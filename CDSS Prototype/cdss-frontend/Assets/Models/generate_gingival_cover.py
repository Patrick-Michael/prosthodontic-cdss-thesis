
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


# ============================================================
# INPUT AND OUTPUT
# ============================================================

SOURCE = Path("clinical_odontogram.glb")

OUTPUT_UPPER = Path("upper_gingival_covers.glb")
OUTPUT_LOWER = Path("lower_gingival_covers.glb")


# ============================================================
# FMA-TO-FDI MAPPING
# ============================================================

TEETH = {
    "11": "FMA55681",
    "12": "FMA55680",
    "13": "FMA55798",
    "14": "FMA55689",
    "15": "FMA55688",
    "16": "FMA55698",
    "17": "FMA55697",

    "21": "FMA55682",
    "22": "FMA55683",
    "23": "FMA55799",
    "24": "FMA55690",
    "25": "FMA55691",
    "26": "FMA55699",
    "27": "FMA55700",

    "31": "FMA57143",
    "32": "FMA57141",
    "33": "FMA55687",
    "34": "FMA55693",
    "35": "FMA55692",
    "36": "FMA55704",
    "37": "FMA55703",

    "41": "FMA57142",
    "42": "FMA57140",
    "43": "FMA55686",
    "44": "FMA55694",
    "45": "FMA55695",
    "46": "FMA55705",
    "47": "FMA55706",
}

GINGIVA = {
    "upper": "FMA59763",
    "lower": "FMA59764",
}

JAW_ROOT = {
    "upper": "UpperJawRoot",
    "lower": "LowerJawRoot",
}

MATERIAL_SOURCE = "FMA52748"


# ============================================================
# GEOMETRY CONFIGURATION
# ============================================================

SEGMENTS = 64
RINGS = 10

# Preserve the preferred recessed appearance.
CONTOUR_SCALE = 1.025
DOME_HEIGHT = 0.25
RIM_INSET = 0.10
MAX_HEIGHT_VARIATION = 0.65

RIM_SMOOTHING = 4

UPPER_PERCENTILES = [
    78, 82, 86, 90, 94, 97
]

LOWER_PERCENTILES = [
    3, 6, 9, 12, 15, 18
]

MIN_CONTOUR_POINTS = 24
MIN_CONTOUR_AREA = 0.75

MAX_GINGIVA_DISTANCE = 5.0

# The two first molars lack separate enamel meshes.
# Their main meshes include long roots, so the usual
# lower-tooth percentages select the wrong region.
#
# These 38th-percentile sections were checked against
# the supplied GLB and are close to the gingival tissue.
MOLAR_SECTION_PERCENTILES = {
    "36": [38],
    "46": [38],
}


# ============================================================
# LOAD THE ORIGINAL MODEL - READ ONLY
# ============================================================

if not SOURCE.is_file():
    raise FileNotFoundError(
        f"Cannot find: {SOURCE.resolve()}"
    )

scene = trimesh.load(
    SOURCE,
    force="scene",
    process=False,
)


def get_mesh(node_name):
    if node_name not in scene.graph.nodes:
        raise ValueError(
            f"Node not found: {node_name}"
        )

    transform, geometry_name = scene.graph[node_name]

    if geometry_name is None:
        raise ValueError(
            f"Node has no geometry: {node_name}"
        )

    mesh = scene.geometry[geometry_name].copy()
    mesh.apply_transform(transform)

    return mesh


def get_tooth_mesh(fma):
    enamel_name = fma + "-enamel"

    if enamel_name in scene.graph.nodes:
        return get_mesh(enamel_name)

    return get_mesh(fma)


# ============================================================
# LOAD GINGIVAL GEOMETRY
# ============================================================

gingiva_meshes = {
    jaw: get_mesh(node_name)
    for jaw, node_name in GINGIVA.items()
}

gingiva_trees = {
    jaw: cKDTree(mesh.vertices)
    for jaw, mesh in gingiva_meshes.items()
}


# ============================================================
# CONTOUR UTILITIES
# ============================================================

def signed_area_xz(points):
    x = points[:, 0]
    z = points[:, 2]

    return 0.5 * np.sum(
        x * np.roll(z, -1)
        - np.roll(x, -1) * z
    )


def resample_closed_contour(points, count):
    points = np.asarray(
        points,
        dtype=float,
    )

    if np.linalg.norm(
        points[0] - points[-1]
    ) < 1e-5:
        points = points[:-1]

    if len(points) < 3:
        raise ValueError(
            "Insufficient contour points"
        )

    closed = np.vstack([
        points,
        points[0],
    ])

    segment_lengths = np.linalg.norm(
        np.diff(closed, axis=0),
        axis=1,
    )

    cumulative = np.concatenate([
        [0.0],
        np.cumsum(segment_lengths),
    ])

    total_length = cumulative[-1]

    if total_length <= 0:
        raise ValueError(
            "Degenerate contour"
        )

    samples = np.linspace(
        0,
        total_length,
        count,
        endpoint=False,
    )

    result = np.zeros((count, 3))

    for dimension in range(3):
        result[:, dimension] = np.interp(
            samples,
            cumulative,
            closed[:, dimension],
        )

    return result


# ============================================================
# EXTRACT CLOSED CROSS-SECTIONS
# ============================================================

def get_section_contours(mesh, height):
    section = mesh.section(
        plane_origin=[
            0.0,
            height,
            0.0,
        ],
        plane_normal=[
            0.0,
            1.0,
            0.0,
        ],
    )

    if section is None:
        return []

    valid = []

    for curve in section.discrete:
        curve = np.asarray(curve)

        if len(curve) < MIN_CONTOUR_POINTS:
            continue

        if np.linalg.norm(
            curve[0] - curve[-1]
        ) > 0.05:
            continue

        curve = resample_closed_contour(
            curve,
            SEGMENTS,
        )

        area = abs(
            signed_area_xz(curve)
        )

        if area < MIN_CONTOUR_AREA:
            continue

        valid.append(curve)

    return valid


# ============================================================
# IDENTIFY THE CERVICAL TOOTH CONTOUR
# ============================================================

def find_cervical_contour(tooth_mesh, jaw, fdi):
    vertices = tooth_mesh.vertices

    # Use the original sampling scheme for 26 teeth.
    if fdi in MOLAR_SECTION_PERCENTILES:
        percentiles = MOLAR_SECTION_PERCENTILES[fdi]
    else:
        percentiles = (
            UPPER_PERCENTILES
            if jaw == "upper"
            else LOWER_PERCENTILES
        )

    tissue_tree = gingiva_trees[jaw]

    candidates = []

    for percentile in percentiles:
        height = float(
            np.percentile(
                vertices[:, 1],
                percentile,
            )
        )

        contours = get_section_contours(
            tooth_mesh,
            height,
        )

        for contour in contours:
            distances, _ = tissue_tree.query(
                contour
            )

            median_distance = float(
                np.median(distances)
            )

            area = abs(
                signed_area_xz(contour)
            )

            candidates.append({
                "contour": contour,
                "height": height,
                "distance": median_distance,
                "area": area,
            })

    if not candidates:
        raise ValueError(
            "No usable closed cervical contour"
        )

    candidates.sort(
        key=lambda candidate: (
            candidate["distance"],
            -candidate["area"],
        )
    )

    selected = candidates[0]

    # Preserve the original geometric validation.
    if selected["distance"] > MAX_GINGIVA_DISTANCE:
        raise ValueError(
            "Cervical contour is too far from gingiva: "
            f"{selected['distance']:.2f}"
        )

    return selected


# ============================================================
# FIT CONTOUR TO GINGIVA - RECESSED VERSION
# ============================================================

def fit_contour_to_gingiva(contour, jaw):
    tissue = gingiva_meshes[jaw].vertices

    reference_y = float(
        np.median(contour[:, 1])
    )

    nearby = tissue[
        np.abs(
            tissue[:, 1] - reference_y
        ) < 3.0
    ]

    if len(nearby) < 20:
        raise ValueError(
            "Not enough gingival vertices near contour"
        )

    horizontal_tree = cKDTree(
        nearby[:, [0, 2]]
    )

    center_xz = np.mean(
        contour[:, [0, 2]],
        axis=0,
    )

    scaled_xz = (
        center_xz
        + (
            contour[:, [0, 2]]
            - center_xz
        ) * CONTOUR_SCALE
    )

    rim_heights = []

    for xz in scaled_xz:
        _, indices = horizontal_tree.query(
            xz,
            k=min(8, len(nearby)),
        )

        indices = np.atleast_1d(
            indices
        )

        rim_heights.append(
            float(
                np.median(
                    nearby[indices, 1]
                )
            )
        )

    rim_heights = np.asarray(
        rim_heights,
        dtype=float,
    )

    reference_height = float(
        np.median(rim_heights)
    )

    rim_heights = np.clip(
        rim_heights,
        reference_height - MAX_HEIGHT_VARIATION,
        reference_height + MAX_HEIGHT_VARIATION,
    )

    for _ in range(RIM_SMOOTHING):
        rim_heights = (
            np.roll(rim_heights, 1)
            + 2.0 * rim_heights
            + np.roll(rim_heights, -1)
        ) / 4.0

    # Preserve the earlier recessed positioning.
    if jaw == "lower":
        rim_heights -= RIM_INSET
    else:
        rim_heights += RIM_INSET

    return np.column_stack([
        scaled_xz[:, 0],
        rim_heights,
        scaled_xz[:, 1],
    ])


# ============================================================
# CONSTRUCT THE RECESSED COVER
# ============================================================

def construct_cover(contour, jaw):
    center = np.mean(
        contour,
        axis=0,
    )

    dome_sign = (
        -1.0 if jaw == "upper"
        else 1.0
    )

    vertices = []
    faces = []

    for ring in range(RINGS):
        fraction = ring / (RINGS - 1)

        radial = (
            1.0 - 0.96 * fraction
        )

        for point in contour:
            position = (
                center
                + (point - center) * radial
            )

            position = position.copy()

            position[1] += (
                dome_sign
                * DOME_HEIGHT
                * (1.0 - radial ** 2)
            )

            vertices.append(position)

    for ring in range(RINGS - 1):
        for segment in range(SEGMENTS):
            next_segment = (
                segment + 1
            ) % SEGMENTS

            a = ring * SEGMENTS + segment
            b = ring * SEGMENTS + next_segment

            c = (ring + 1) * SEGMENTS + segment
            d = (ring + 1) * SEGMENTS + next_segment

            faces.append([a, b, c])
            faces.append([b, d, c])

    apex_index = len(vertices)

    apex = center.copy()
    apex[1] += (
        dome_sign * DOME_HEIGHT
    )

    vertices.append(apex)

    last_ring = (
        (RINGS - 1) * SEGMENTS
    )

    for segment in range(SEGMENTS):
        next_segment = (
            segment + 1
        ) % SEGMENTS

        faces.append([
            last_ring + segment,
            last_ring + next_segment,
            apex_index,
        ])

    cover = trimesh.Trimesh(
        vertices=np.asarray(vertices),
        faces=np.asarray(faces),
        process=False,
    )

    cover.fix_normals()

    return cover


# ============================================================
# MUCOSAL MATERIAL
# ============================================================

mucosa_mesh = get_mesh(
    MATERIAL_SOURCE
)

mucosa_material = (
    mucosa_mesh.visual.material
)

if mucosa_material is None:
    raise ValueError(
        "Mucosa material unavailable"
    )

mucosa_color = (
    mucosa_material.baseColorFactor
)

if mucosa_color is None:
    raise ValueError(
        "Mucosa base color unavailable"
    )


def apply_mucosa_material(cover):
    material = trimesh.visual.material.PBRMaterial(
        name="MucosaCover",
        baseColorFactor=list(mucosa_color),
        metallicFactor=0.0,
        roughnessFactor=(
            float(mucosa_material.roughnessFactor)
            if mucosa_material.roughnessFactor is not None
            else 0.9
        ),
        doubleSided=True,
    )

    cover.visual = trimesh.visual.TextureVisuals(
        material=material
    )


# ============================================================
# GENERATE ALL 28 COVERS
# ============================================================

outputs = {
    "upper": trimesh.Scene(),
    "lower": trimesh.Scene(),
}

successful = {
    "upper": [],
    "lower": [],
}

failures = []


for fdi, fma in TEETH.items():
    jaw = (
        "upper"
        if fdi[0] in ("1", "2")
        else "lower"
    )

    try:
        tooth_mesh = get_tooth_mesh(fma)

        selected = find_cervical_contour(
            tooth_mesh,
            jaw,
            fdi,
        )

        fitted_contour = fit_contour_to_gingiva(
            selected["contour"],
            jaw,
        )

        cover = construct_cover(
            fitted_contour,
            jaw,
        )

        apply_mucosa_material(
            cover
        )

        # Use the jaw's local coordinate system so
        # the cover follows the existing jaw animation.
        jaw_transform, _ = scene.graph[
            JAW_ROOT[jaw]
        ]

        cover.apply_transform(
            np.linalg.inv(jaw_transform)
        )

        cover_name = (
            f"Cover_{fdi}"
        )

        outputs[jaw].add_geometry(
            cover,
            geom_name=cover_name,
            node_name=cover_name,
        )

        successful[jaw].append(
            fdi
        )

        print(
            f"{cover_name}: "
            f"section Y={selected['height']:.2f}, "
            f"gingiva distance="
            f"{selected['distance']:.2f}, "
            f"area={selected['area']:.2f}"
        )

    except Exception as exc:
        failures.append((
            fdi,
            str(exc),
        ))

        print(
            f"FAILED Cover_{fdi}: {exc}"
        )


# ============================================================
# EXPORT AND VALIDATION
# ============================================================

total = (
    len(successful["upper"])
    + len(successful["lower"])
)

print()
print("RECESSED TOOTH-CONTOUR COVER GENERATION")
print("-" * 44)

print(
    "Upper:",
    len(successful["upper"]),
    "/14",
)

print(
    "Lower:",
    len(successful["lower"]),
    "/14",
)

print(
    "Total:",
    total,
    "/28",
)

if failures:
    print()
    print("FAILED COVERS:")

    for fdi, error in failures:
        print(
            f"FDI {fdi}: {error}"
        )

    # Preserve the existing GLBs if any tooth failed.
    raise RuntimeError(
        "Cover generation incomplete. "
        "Existing GLBs were not overwritten."
    )

# Export only after all 28 covers are generated.
outputs["upper"].export(
    OUTPUT_UPPER
)

outputs["lower"].export(
    OUTPUT_LOWER
)

print()
print("Exported:", OUTPUT_UPPER)
print("Exported:", OUTPUT_LOWER)
print("All 28 covers generated.")
