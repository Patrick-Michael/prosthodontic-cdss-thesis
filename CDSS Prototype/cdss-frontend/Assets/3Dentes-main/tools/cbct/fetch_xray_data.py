#!/usr/bin/env python3
"""Fetch NIST X-ray mass attenuation data -> tools/xray-mass-attenuation.json.

    ~/projects/3Dentes-cbct/nnunet-venv/bin/python tools/cbct/fetch_xray_data.py

Run once; the output is committed. This exists so the numbers in that JSON have
a provenance a reader can re-run, rather than being coefficients that appeared
in a commit with nobody able to say where from.

Two things come back:

  elements   per-element mu/rho against energy, for the elements that occur in
             dental tissue. The MIXTURE RULE builds any compound from these:
             (mu/rho)_compound = sum_i w_i (mu/rho)_i, exact for the photon
             energies that matter here because attenuation is per-atom.

  materials  the ICRU-44 tissue compositions and densities from NIST table 2.
             Cortical bone, soft tissue, water and air come from here rather
             than from anything I typed, and water and cortical bone double as
             the test targets for the mixture rule (see attenuation.test.mjs).

ABSORPTION EDGES ARE REAL DATA, NOT DUPLICATES. Zirconium's K edge sits at
17.998 keV and yttrium's at 17.038 -- both INSIDE the diagnostic range, and both
in the zirconia crowns on 19 and 30. The tables list such an energy twice, once
either side of the jump. Keep both rows in order; dropping either flattens a
factor-of-four step in the crown's own attenuation.
"""
import json
import os
import re
import sys
import urllib.request

BASE = "https://physics.nist.gov/PhysRefData/XrayMassCoef"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "xray-mass-attenuation.json")

# Everything that occurs above trace level in enamel, dentin, pulp, bone, PDL,
# air, or in 3Y-TZP zirconia.
ELEMENTS = {1: "H", 6: "C", 7: "N", 8: "O", 11: "Na", 12: "Mg", 15: "P",
            16: "S", 17: "Cl", 18: "Ar", 19: "K", 20: "Ca", 39: "Y", 40: "Zr"}

# Pulled from NIST table 2 by exact name. These carry both a composition and a
# density, so they are used directly rather than rebuilt.
MATERIALS = ["Water, Liquid", "Bone, Cortical (ICRU-44)", "Tissue, Soft (ICRU-44)",
             "Air, Dry (near sea level)", "Adipose Tissue (ICRU-44)",
             "Muscle, Skeletal (ICRU-44)"]

# NIST also publishes mu/rho for these materials as compounds. Fetching those
# gives the mixture rule an INDEPENDENT check: build the compound from elements,
# compare against NIST's own answer for the same compound. attenuation.test.mjs
# does exactly that, and it is the only thing standing between a plausible
# density model and a wrong one.
COMPOUND_TABLES = {"Water, Liquid": "water",
                   "Bone, Cortical (ICRU-44)": "bone",
                   "Tissue, Soft (ICRU-44)": "tissue",
                   "Adipose Tissue (ICRU-44)": "adipose",
                   "Muscle, Skeletal (ICRU-44)": "muscle",
                   "Air, Dry (near sea level)": "air"}

NUM = re.compile(r"\d\.\d+E[+-]\d+")
UA = "3Dentes-atlas/0.7 (dental anatomy atlas; contact via github.com/NateSaindon/dotfiles)"


def get(url, cache):
    path = os.path.join(cache, re.sub(r"[^A-Za-z0-9._-]", "_", url.split("/", 4)[-1]))
    if os.path.exists(path):
        return open(path, encoding="latin-1").read()
    # NIST answers 403 to urllib's default agent; identify properly.
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("latin-1")
    os.makedirs(cache, exist_ok=True)
    open(path, "w", encoding="latin-1").write(text)
    return text


def parse_element(html):
    """-> (energies_MeV, mu_over_rho). Rows are (E, mu/rho, mu_en/rho)."""
    body = html[html.index("(MeV)"):] if "(MeV)" in html else html
    nums = [float(x) for x in NUM.findall(body)]
    if len(nums) % 3:
        raise ValueError(f"not a whole number of rows: {len(nums)} values")
    rows = [nums[i:i + 3] for i in range(0, len(nums), 3)]
    return [r[0] for r in rows], [r[1] for r in rows]


def parse_materials(html):
    out = {}
    for block in re.findall(r"<TR VALIGN=\"top\">(.*?)</TR>", html, re.S):
        tds = re.findall(r"<TD[^>]*>(.*?)</TD>", block, re.S)
        if len(tds) < 5:
            continue
        name = re.sub(r"<[^>]*>", "", tds[0]).strip().replace("\xa0", " ")
        if name not in MATERIALS:
            continue
        comp = {}
        for z, frac in re.findall(r"(\d+):\s*([\d.]+)", re.sub(r"<[^>]*>", " ", tds[4])):
            comp[int(z)] = float(frac)
        out[name] = {"density_g_cm3": float(re.sub(r"<[^>]*>", "", tds[3]).strip()),
                     "composition_by_weight": comp}
    return out


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else "/tmp/nist-xray-cache"
    elements = {}
    for z, sym in ELEMENTS.items():
        e, mu = parse_element(get(f"{BASE}/ElemTab/z{z:02d}.html", cache))
        elements[str(z)] = {"symbol": sym, "energy_MeV": e, "mu_over_rho_cm2_g": mu}
        print(f"  Z={z:<3d} {sym:<3s} {len(e):3d} rows  "
              f"{e[0]*1e3:.0f} keV .. {e[-1]*1e3:.0f} keV")

    materials = parse_materials(get(f"{BASE}/tab2.html", cache))
    missing = [m for m in MATERIALS if m not in materials]
    if missing:
        sys.exit(f"NIST table 2 did not yield: {missing}")
    for name, m in materials.items():
        total = sum(m["composition_by_weight"].values())
        if abs(total - 1.0) > 5e-3:
            sys.exit(f"{name}: weight fractions sum to {total}, not 1")
        print(f"  {name:<34s} rho={m['density_g_cm3']:.4f}  "
              f"{len(m['composition_by_weight'])} elements")

    for name, slug in COMPOUND_TABLES.items():
        e, mu = parse_element(get(f"{BASE}/ComTab/{slug}.html", cache))
        materials[name]["reference_energy_MeV"] = e
        materials[name]["reference_mu_over_rho_cm2_g"] = mu
        print(f"  reference table   {name:<34s} {len(e)} rows")

    json.dump({
        "source": "NIST X-Ray Mass Attenuation Coefficients (Hubbell & Seltzer, "
                  "NISTIR 5632); element tables and table 2 tissue compositions",
        "url": BASE,
        "note": "Duplicate energies are absorption edges and are intentional; "
                "keep both rows and interpolate within segments.",
        "elements": elements,
        "materials": materials,
    }, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
