// Digitally reconstructed radiograph, on the GPU.
//
// Phase 3 of docs/drr-plan.md. The algorithm is the one validated on the CPU in
// tools/cbct/drr_mesh.py, and that script stays the reference: when this
// disagrees with it, this is what is wrong.
//
// THE IDEA. For a closed surface the path length a ray spends inside it is
//
//     sum(distance at back faces) - sum(distance at front faces)
//
// because every entry has a matching exit. So no sorting, no depth peeling and
// no CSG: render every mesh once with additive blending, back faces positive
// and front faces negative, and read the path length straight out of the buffer.
// It is also why Phase 2 spent its effort making every mesh closed and outward
// wound — an inverted solid subtracts itself from the image.
//
// NO MULTIPLE RENDER TARGETS ARE USED, deliberately. Each tissue writes into one
// CHANNEL of an RGBA target, so four tissues accumulate per target in a single
// pass and the seven we need fit in two. That keeps this working on hardware
// with no MRT support, which is most of the reason it should run on a phone.
//
// PRECISION. Distances from the source run 250-350 mm, where half float
// resolves only ~0.25 mm — useless for a 2 mm path. Depth is therefore emitted
// relative to a reference distance, keeping values within about +/-50 mm where
// the resolution is ~0.03 mm, well under the 0.16 mm voxel. Subtracting a
// constant is EXACT here, not an approximation: each solid contributes as many
// back faces as front faces, so the constant cancels in the difference.

import * as THREE from 'three';

// Which tissue channel each layer's meshes accumulate into. `tooth` and `bone`
// are BULK: dentin is the tooth less its enamel, pulp and crown, and trabecular
// bone is the bone mesh less the lamina dura inside it. Both subtractions
// happen per pixel in the composite, so neither needs CSG on the geometry.
//
// Nerves and vessels are absent on purpose: soft tissue inside bone, whose
// attenuation is far below the geometric error, so drawing them would add
// nothing a reader could see.
// Measured separation between cortical and medullary bone in this patient's
// volume, in uncalibrated grey units: 854.7 - 631.7, from
// tools/cbct/trabecular_isolate.py on the centred exposure. It is the
// denominator that turns the field's grey values into attenuation -- see
// setEnergy. Re-measure it if the isolation parameters change.
// The detector's latitude: the span of attenuation one exposure can record,
// fixed across every film. MEASURED as the widest the old per-film fit ever
// chose (tooth 3, 7.19) so that nothing which used to be visible is now
// clipped -- the change should cost anteriors their false contrast, not cost
// posteriors their dense end.
const LATITUDE = 7.2;
/**
 * Where the display window starts, in tau. ZERO IS AIR.
 *
 * `autoWindow` fitted this per film as the 2nd percentile of tau below the
 * metal cut. Measured across all 28 teeth after 0.9.0 fixed the latitude
 * (drr.html?window=1), that fit lands in the same place every single time:
 *
 *     offset range      -0.14 .. 0.00   against a latitude of 7.20
 *     spread             0.14  = 1.9% of the latitude
 *     anteriors  mean   -0.037
 *     posteriors mean   -0.061   -> a 0.3% difference
 *
 * It is pinned because every periapical has AIR in the field, so the 2nd
 * percentile sits at zero attenuation whatever the anatomy is. Fitting it was
 * measuring the air, once per render.
 *
 * So it becomes a constant, and the constant is 0 rather than the -0.05 mean:
 * the window starts at zero attenuation and spans one latitude, which is what
 * a detector does. The difference from the fitted mean is 0.7% of the range.
 */
const WINDOW_LO = 0.0;

const GREY_SEPARATION = 223.0;

// Gain on the measured trabecular modulation. THE ONE TUNED NUMBER IN THE
// RADIOGRAPH, and it is fitted rather than chosen by eye.
//
// WHY A GAIN IS NEEDED AT ALL. Applied at unity the field is faithful and too
// faint, for two reasons that are both real and neither a bug. A zero-mean
// field integrated through ~12 mm of bone with ~1 mm correlation length
// averages down by about sqrt(12) -- positive and negative deviations cancel
// along the ray, where real trabecular plates are coherent along the beam in a
// way a 0.48 mm sampling is not. And the CBCT had already blurred the contrast
// before we measured it: 0.16 mm voxels with a worse point spread average
// trabecula with marrow, so the measured sd of 152 grey UNDERSTATES the true
// bone/marrow difference.
//
// HOW IT WAS FITTED. Against the operator's own periapical of 31/30/29 -- same
// patient, same teeth -- comparing structure at 1-3 mm inside pure trabecular
// bone, normalised by each image's own overall contrast so his sensor's gamma
// and our auto-window divide out, and filtered at a fixed PHYSICAL scale
// because his film is 66.7 px/mm and ours about 25. His ratio is 0.0904, ours
// at unity gain 0.0359.
//
// SAY WHAT THIS IS. The pattern is measured, the two-point grey-to-attenuation
// calibration is derived, and this amplitude is TUNED to a measured target. The
// operator's argument for allowing it is on the record and is a fair one: every
// other measured structure here is Taubin-smoothed and decimated, so measured
// geometry has always been processed for presentation. The distinction kept in
// view is that smoothing preserves the quantity claimed while a gain changes
// it, which is exactly why it lives here as one named constant with its
// derivation attached rather than folded invisibly into uMuPerGrey.
const TRABECULAR_GAIN = 2.25;

// How hard superimposed structure fades behind dense tissue, per unit of the
// tooth's own attenuation.
//
// SWEPT, against the field's own contribution isolated by differencing each
// render against the same render with no field -- which is the only way to
// separate superimposed trabeculae from the tooth's OWN internal anatomy, and
// the reason a first attempt at this measurement saturated at a meaningless
// 0.63 (the hand-picked "tooth" box had bone gaps in it, where the shoulder
// does nothing by construction).
//
//   shoulder   over dentin   over bone   dentin/bone
//      0.0        5.147        7.096        0.725
//      0.5        2.771        6.676        0.415
//      1.0        2.054        6.496        0.316
//      2.0        1.547        6.333        0.244
//      4.0        1.281        6.219        0.206
//
// 0.5 roughly halves the show-through and deliberately does NOT abolish it:
// trabeculae ARE visible through dentin on a real periapical, which is the
// operator's own description of the defect. The floor for very dense tissue is
// his zirconia at 0.286, and dentin should sit above that floor rather than on
// it.
//
// NOTE THE CROWN BARELY MOVES across that sweep (0.902 -> 0.907). Rays through
// a crown pass through almost no bone, because the crown is coronal to the
// alveolar crest, so the field never had much to contribute there. The problem
// was always the roots, which sit in bone.
//
// The gain was re-fitted afterwards. It went 2.5 -> 2.7 -> 2.25, and the detour
// is worth recording: the first re-fit used a mask covering the field's whole
// footprint, which now includes the dentin the shoulder has just suppressed, so
// it reported the film as too FAINT and pushed the gain up. Comparing pure bone
// against his pure-bone crops -- like for like, which is what the PA side had
// always measured -- said the opposite. Fit on matched regions or the shoulder
// and the gain chase each other.
let SHOULDER = 0.5;
/** For sweeping the shoulder from a URL param; not part of the shipped path. */
export function setShoulderConstant(v) { SHOULDER = v; }

export const CHANNELS = {
  A: [['teeth', 'tooth'], ['enamel', 'enamel'], ['pulp', 'pulp'],
      ['prosthetic', 'zirconia']],
  B: [['mandible|maxilla|midface|ramus', 'bone'], ['lamina', 'corticalBone'],
      ['pdl', 'pdl'], ['gingiva', 'gingiva']],
};

const ACC_VERT = /* glsl */`
  varying vec3 vView;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vView = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const ACC_FRAG = /* glsl */`
  precision highp float;
  varying vec3 vView;
  uniform vec4 uChannel;
  uniform float uRef;      // reference distance; cancels exactly in the sum
  uniform float uRecD;     // source -> receptor, along the view axis

  void main() {
    float dist = length(vView);
    // THE RECEPTOR IS OPAQUE. Clamping each intersection to the receptor's own
    // distance is exact, not an approximation: a solid wholly behind the sensor
    // contributes R - R = 0, one wholly in front is untouched, and one that
    // straddles contributes R - d_front, which is the part in front of it.
    float R = uRecD * dist / max(-vView.z, 1e-6);
    float d = min(dist, R) - uRef;
    gl_FragColor = uChannel * (gl_FrontFacing ? -d : d);
  }
`;

const QUAD_VERT = /* glsl */`
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

// Beer-Lambert, then the display window. The window is applied here rather than
// baked into the accumulation so kVp and exposure stay live controls.
const COMPOSITE_FRAG = /* glsl */`
  precision highp float;
  varying vec2 vUv;
  uniform sampler2D tA, tB, tT;
  uniform bool uHasField;
  uniform float uMuPerGrey;
  uniform float uShoulder;
  uniform float muEnamel, muDentin, muPulp, muZirconia;
  uniform float muCortical, muTrabecular, muPdl, muGingiva;
  uniform float uLo, uHi, uGamma;
  uniform bool uTauOut;
  uniform vec3 uPa, uEdgeR, uEdgeU;   // receptor corner and edges, in view space
  uniform vec3 uBeamAxis;             // beam axis, in view space
  uniform float uBeamCos;             // cos of the beam's half angle

  float tauAt(vec2 uv) {
    vec4 A = texture2D(tA, uv);
    vec4 B = texture2D(tB, uv);
    float dentin = max(0.0, A.r - A.g - A.b - A.a);
    float trab   = max(0.0, B.r - B.g);
    float tau = muEnamel * A.g + muDentin * dentin + muPulp * A.b
         + muZirconia * A.a + muCortical * B.g + muTrabecular * trab
         + muPdl * B.b + muGingiva * B.a;
    // THE MEASURED TRABECULAR MODULATION, which cannot ride on a path length.
    //
    // Everything above is (path length x bulk mu): one number per tissue per
    // pixel, with no record of WHERE along the ray the tissue was. A density
    // field that varies along the ray cannot be applied that way, so tT carries
    // its own line integral from the march pass -- grey-value excess times
    // millimetres -- and only the conversion to attenuation happens here.
    //
    // GATED BY THE BONE PATH LENGTH. The field's support is the isolated-bone
    // mask and the silhouette here is the bone MESH; they come from the same
    // segmentation and agree closely, but not exactly. Ramping over the first
    // millimetre of bone keeps the modulation from printing outside the bone
    // it belongs to, which would read as a halo around the jaw.
    if (uHasField) {
      // SUPERIMPOSED STRUCTURE FADES OVER DENSE TISSUE, and without this the
      // trabeculae print through the roots far harder than they do on a real
      // film -- the operator's read, 2026-09-06, and his own periapical
      // measures it: the zirconia crown is internally uniform, so ALL the
      // structure on it is superimposed, and it carries sd 1.175 against 4.106
      // in open bone. A suppression to 0.29 behind dense tissue.
      //
      // It is a REAL sensor property, not a fudge. A detector's response
      // compresses at the dense end, so a fixed increment of attenuation moves
      // the displayed value less there than it does in the midtones. This
      // composite's stretch is linear and models none of that, which is why
      // ours showed the same trabecular amplitude over a root as beside it.
      //
      // Applied to the MODULATION rather than to the whole image on purpose:
      // compressing the composite globally would also flatten the enamel-dentin
      // boundary and the lamina dura, which are the features the film exists to
      // show, and which his PA renders crisply at the same densities.
      float toothTau = muEnamel * A.g + muDentin * dentin + muZirconia * A.a;
      float shoulder = 1.0 / (1.0 + uShoulder * toothTau);
tau += uMuPerGrey * texture2D(tT, uv).r * min(1.0, trab) * shoulder;
    }
    return tau;
  }

  void main() {
    float tau = tauAt(vUv);
    if (uTauOut) { gl_FragColor = vec4(tau, 0.0, 0.0, 1.0); return; }
    float v = clamp((tau - uLo) / max(uHi - uLo, 1e-6), 0.0, 1.0);
    v = pow(v, uGamma);
    // CONE CUT. The source sits at the view origin, so the ray to this pixel is
    // just the direction of its point on the receptor. Outside the beam's cone
    // the film was never exposed, and unexposed film is BLACK -- the opposite
    // end of the scale from the dense structures, which is exactly why a cone
    // cut is unmistakable on a real radiograph.
    vec3 p = uPa + uEdgeR * vUv.x + uEdgeU * vUv.y;
    if (dot(normalize(p), uBeamAxis) < uBeamCos) v = 0.0;
    gl_FragColor = vec4(v, v, v, 1.0);
  }
`;

// The measured trabecular field, integrated along each ray.
//
// WHY A SECOND PASS AND NOT A CHANNEL. The accumulation above is a path-length
// trick: back faces minus front faces, no sorting, no marching. It is exact and
// it is cheap, and it throws away all positional information -- which is fine
// for a bulk density and useless for one that varies. So the field gets its own
// pass, and this one really does march.
//
// IT IS AFFORDABLE because it marches only the field's bounding box, ~82 mm,
// not the 300 mm source-to-receptor distance. At 0.48 mm that is ~170 steps on
// a film a few hundred pixels across.
//
// GLSL3, because sampler3D does not exist in GLSL ES 1.00. WebGL2 is already
// required for the float render targets, so this adds no new hardware demand.
const MARCH_VERT = /* glsl */`
  out vec2 vUv;
  void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

const MARCH_FRAG = /* glsl */`
  precision highp float;
  precision highp sampler3D;
  in vec2 vUv;
  layout(location = 0) out vec4 fragColor;

  uniform sampler3D uField;
  uniform vec3 uSource;                  // world mm
  uniform vec3 uPaW, uEdgeRW, uEdgeUW;   // receptor corner and edges, world mm
  uniform vec3 uFieldMin, uFieldMax;     // field AABB, world mm
  uniform float uStep;                   // march step, mm
  uniform float uLsb;                    // grey units per LSB
  uniform float uZero;                   // the no-modulation level, 0..255

  void main() {
    vec3 P = uPaW + uEdgeRW * vUv.x + uEdgeUW * vUv.y;
    vec3 ray = P - uSource;
    float len = length(ray);
    vec3 dir = ray / len;

    // Slab test. A ray missing the jaw entirely costs one branch.
    vec3 inv = 1.0 / dir;
    vec3 ta = (uFieldMin - uSource) * inv;
    vec3 tb = (uFieldMax - uSource) * inv;
    float tn = max(max(min(ta.x, tb.x), min(ta.y, tb.y)), min(ta.z, tb.z));
    float tf = min(min(max(ta.x, tb.x), max(ta.y, tb.y)), max(ta.z, tb.z));
    tn = max(tn, 0.0);
    // THE RECEPTOR IS OPAQUE here too, exactly as in the accumulation pass:
    // bone behind the sensor was never imaged, and integrating it would print
    // the far cortex of the opposite side onto the film.
    tf = min(tf, len);
    if (tf <= tn) { fragColor = vec4(0.0); return; }

    float span = tf - tn;
    int n = int(min(ceil(span / uStep), 512.0));
    float h = span / float(n);
    // JITTER THE START, per pixel. Marching a 0.48 mm field in 0.48 mm steps
    // puts the sample points on a lattice, and wherever a ray runs near-parallel
    // to a texture axis the two beat against each other -- which printed as
    // horizontal banding across the upper molar films, an artefact of the
    // sampler and not of any anatomy. A hash offset within one step turns that
    // coherent moire into incoherent noise, which the eye does not read as
    // structure. Costs one extra fract().
    float jitter = fract(sin(dot(vUv, vec2(12.9898, 78.233))) * 43758.5453);
    float acc = 0.0;
    vec3 ext = uFieldMax - uFieldMin;
    for (int i = 0; i < 512; i++) {
      if (i >= n) break;
      vec3 p = uSource + dir * (tn + (float(i) + jitter) * h);
      // Outside bone the field is stored AT THE ZERO LEVEL, so the mask comes
      // for free: empty space contributes nothing without a second lookup.
      acc += texture(uField, (p - uFieldMin) / ext).r * 255.0 - uZero;
    }
    fragColor = vec4(acc * h * uLsb, 0.0, 0.0, 1.0);
  }
`;

/** IEEE 754 half -> float, for reading back a half-float target. */
function halfToFloat(h) {
  const sign = (h & 0x8000) ? -1 : 1;
  const exp = (h & 0x7c00) >> 10;
  const frac = h & 0x03ff;
  if (exp === 0) return sign * Math.pow(2, -14) * (frac / 1024);
  if (exp === 0x1f) return frac ? NaN : sign * Infinity;
  return sign * Math.pow(2, exp - 15) * (1 + frac / 1024);
}

/** What this device can actually do. Reported, never assumed. */
export function capabilities(renderer) {
  const gl = renderer.getContext();
  const isWebGL2 = renderer.capabilities.isWebGL2 !== false
    && typeof WebGL2RenderingContext !== 'undefined'
    && gl instanceof WebGL2RenderingContext;
  const has = (n) => !!gl.getExtension(n);
  const colorBufferFloat = has('EXT_color_buffer_float');
  const colorBufferHalf = has('EXT_color_buffer_half_float');
  return {
    isWebGL2,
    colorBufferFloat,
    colorBufferHalf,
    floatBlend: has('EXT_float_blend'),
    maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
    renderer: (() => {
      const d = gl.getExtension('WEBGL_debug_renderer_info');
      return d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'unknown';
    })(),
    // Half float is what this needs: 32-bit blending additionally requires
    // EXT_float_blend, which is far less widely available on mobile.
    ok: isWebGL2 && (colorBufferFloat || colorBufferHalf),
  };
}

/**
 * Fetch the measured trabecular field, or null if it is not there.
 *
 * NULL IS A SUPPORTED ANSWER, not an error. The field is 4 MB of the build's
 * 20, and every path through this app has to keep working without it: an older
 * cached service worker, a partial deploy, a device that ran out of room. The
 * radiograph without it is exactly the radiograph that shipped in 0.8.0.
 */
export async function loadField(base) {
  try {
    const [meta, buf] = await Promise.all([
      fetch(`${base}trabecular.json`).then((r) => (r.ok ? r.json() : null)),
      fetch(`${base}trabecular.bin`).then((r) => (r.ok ? r.arrayBuffer() : null)),
    ]);
    if (!meta || !buf) return null;
    return { data: new Uint8Array(buf), meta };
  } catch {
    return null;
  }
}

export function createDRR(renderer, structures, attenuation) {
  const caps = capabilities(renderer);
  if (!caps.ok) return { caps, ok: false };

  const scene = new THREE.Scene();
  // A bare Camera, not a PerspectiveCamera: place() writes the projection
  // matrix itself, and a PerspectiveCamera would recompute it from fov.
  const camera = new THREE.Camera();
  const groups = { A: [], B: [] };

  const target = (w, h) => new THREE.WebGLRenderTarget(w, h, {
    type: THREE.HalfFloatType,
    format: THREE.RGBAFormat,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: false,
    stencilBuffer: false,
  });

  // The tau buffer is READ BACK, so its type has to be one readPixels can
  // return. A half-float target does not read into a Float32Array -- that was
  // the first version, autoWindow silently returned nothing, the window stayed
  // at its default and the whole film blew out white. 32-bit float needs no
  // blending here (one full-screen pass, no accumulation), so EXT_float_blend
  // is not required; where even that is unavailable we read raw halves and
  // decode them.
  const tauFloat = caps.colorBufferFloat;
  const rtTau = new THREE.WebGLRenderTarget(2, 2, {
    type: tauFloat ? THREE.FloatType : THREE.HalfFloatType,
    format: THREE.RGBAFormat,
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    depthBuffer: false,
    stencilBuffer: false,
  });
  let rtA = target(2, 2), rtB = target(2, 2);
  // The march writes one number per pixel, but a single-channel float target is
  // not universally renderable while RGBA half-float already is -- the same
  // target type the accumulation uses and the same reason.
  let rtT = target(2, 2);
  let width = 0, height = 0;
  let field = null;

  const march = new THREE.ShaderMaterial({
    vertexShader: MARCH_VERT,
    fragmentShader: MARCH_FRAG,
    glslVersion: THREE.GLSL3,
    uniforms: {
      uField: { value: null },
      uSource: { value: new THREE.Vector3() },
      uPaW: { value: new THREE.Vector3() },
      uEdgeRW: { value: new THREE.Vector3() },
      uEdgeUW: { value: new THREE.Vector3() },
      uFieldMin: { value: new THREE.Vector3() },
      uFieldMax: { value: new THREE.Vector3() },
      uStep: { value: 0.48 },
      uLsb: { value: 1 },
      uZero: { value: 128 },
    },
    depthTest: false, depthWrite: false,
  });
  const marchScene = new THREE.Scene().add(
    new THREE.Mesh(new THREE.PlaneGeometry(2, 2), march));

  const composite = new THREE.ShaderMaterial({
    vertexShader: QUAD_VERT,
    fragmentShader: COMPOSITE_FRAG,
    uniforms: {
      tA: { value: rtA.texture }, tB: { value: rtB.texture },
      tT: { value: null }, uHasField: { value: false },
      uMuPerGrey: { value: 0 }, uShoulder: { value: 0 },
      muEnamel: { value: 0 }, muDentin: { value: 0 }, muPulp: { value: 0 },
      muZirconia: { value: 0 }, muCortical: { value: 0 },
      muTrabecular: { value: 0 }, muPdl: { value: 0 }, muGingiva: { value: 0 },
      uLo: { value: 0 }, uHi: { value: 6 }, uGamma: { value: 1 },
      uTauOut: { value: false },
      uPa: { value: new THREE.Vector3() },
      uEdgeR: { value: new THREE.Vector3() },
      uEdgeU: { value: new THREE.Vector3() },
      uW2C: { value: new THREE.Matrix4() },
      uBeamAxis: { value: new THREE.Vector3(0, 0, -1) },
      uBeamCos: { value: -1 },
    },
    depthTest: false, depthWrite: false,
  });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), composite);
  const quadScene = new THREE.Scene().add(quad);
  const quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  /**
   * Build the accumulation scene from the loaded meshes.
   *
   * Geometry is SHARED with the 3D view rather than copied — these are the same
   * buffers, wearing a different material. Nothing here mutates the meshes the
   * atlas is already showing.
   */
  const sources = new Map();

  function build(meshes) {
    for (const key of ['A', 'B']) {
      for (const [i, [layerSpec, tissue]] of CHANNELS[key].entries()) {
        const layers = new Set(layerSpec.split('|'));
        const channel = [0, 0, 0, 0];
        channel[i] = 1;
        const material = new THREE.ShaderMaterial({
          vertexShader: ACC_VERT,
          fragmentShader: ACC_FRAG,
          uniforms: {
            uChannel: { value: new THREE.Vector4(...channel) },
            uRef: { value: 300 },
            uRecD: { value: 300 },
          },
          side: THREE.DoubleSide,
          transparent: true,
          blending: THREE.CustomBlending,
          blendEquation: THREE.AddEquation,
          blendSrc: THREE.OneFactor,
          blendDst: THREE.OneFactor,
          depthTest: false,
          depthWrite: false,
        });
        const members = [];
        for (const [fma, mesh] of meshes) {
          if (!layers.has(structures[fma]?.layer)) continue;
          const m = new THREE.Mesh(mesh.geometry, material);
          mesh.updateWorldMatrix(true, false);
          m.matrixAutoUpdate = false;
          m.matrix.copy(mesh.matrixWorld);
          m.frustumCulled = false;
          scene.add(m);
          // Keep the SOURCE mesh, not just its matrix. These copies have
          // matrixAutoUpdate off and were frozen at build time, so anything
          // that moves the anatomy afterwards -- opening the mouth for an
          // exposure -- has to be able to bring them along, or the film and
          // the 3D view stop describing the same mouth.
          members.push(m);
          sources.set(m, mesh);
        }
        groups[key].push({ tissue, material, members, count: members.length });
      }
    }
    return groups;
  }

  function resize(w, h) {
    if (w === width && h === height) return;
    width = w; height = h;
    rtA.setSize(w, h); rtB.setSize(w, h); rtT.setSize(w, h);
    // The window is a PERCENTILE, so it needs enough samples to be stable. At
    // the atlas panel's ~245 px the 1/8 grid is only 30 px across, and the
    // window then jitters between renders for no reason the user can see. Floor
    // it at 64 wide: still trivial to read back, and enough to be steady.
    rtTau.setSize(Math.max(64, w >> 3), Math.max(45, h >> 3));
    composite.uniforms.tA.value = rtA.texture;
    composite.uniforms.tB.value = rtB.texture;
    composite.uniforms.tT.value = rtT.texture;
  }

  /**
   * Place the source and the receptor, as a real exposure is placed.
   *
   * GENERALIZED PERSPECTIVE, not a look-at camera. A THREE.PerspectiveCamera
   * always puts its image plane perpendicular to the view direction, which can
   * only ever express the PARALLELING technique. The bisecting technique tilts
   * the receptor against the tooth's long axis and aims the central ray at the
   * bisector, so the film is oblique to the beam -- and the foreshortening and
   * elongation that produces is precisely what the technique has to teach. A
   * perpendicular image plane cannot show it at all.
   *
   * So the projection is built from the receptor RECTANGLE and the source
   * point (Kooima's construction): an orthonormal basis on the receptor, an
   * off-axis frustum whose extents are the corners as seen from the source.
   * Foreshortening then falls out of the geometry rather than being an effect
   * anyone authored.
   *
   * `pa`, `pb`, `pc` are the receptor's bottom-left, bottom-right and top-left
   * corners in world millimetres.
   */
  function place({ source, pa, pb, pc }) {
    const vr = pb.clone().sub(pa).normalize();
    const vu = pc.clone().sub(pa).normalize();
    const vn = new THREE.Vector3().crossVectors(vr, vu).normalize();

    const va = pa.clone().sub(source);
    const vb = pb.clone().sub(source);
    const vc = pc.clone().sub(source);

    // Perpendicular distance from the source to the receptor PLANE.
    //
    // THIS REFUSES RATHER THAN CORRECTING ITSELF, and that is deliberate. The
    // corner order defines which face of the film the source is on. An earlier
    // version "fixed" a source behind the plane by negating vr, which silently
    // MIRRORED the image: left and right swapped, and the picture still looked
    // like a perfectly good radiograph. On a radiograph that is not a cosmetic
    // bug — laterality is the one thing a film must never lie about, and a
    // mirrored periapical points a clinician at the wrong side of the mouth.
    //
    // It also flipped the screen-space winding, which inverted gl_FrontFacing
    // and turned every path length negative, so dense tissue came out BLACK.
    // That is what made it visible. It would not always be.
    //
    // Callers order the corners so the source is on the front: pass the
    // receptor's horizontal as cross(up, toSource).
    const d = -va.dot(vn);
    if (!(d > 0)) {
      throw new Error(
        'DRR: the source is behind the receptor. Corner order decides which '
        + 'face of the film is exposed, and correcting it here would mirror '
        + 'the radiograph. Pass pa/pb/pc with cross(pb-pa, pc-pa) pointing at '
        + 'the source.');
    }

    const near = Math.max(1, d - 140);
    const far = d + 140;
    const k = near / d;
    const left = vr.dot(va) * k, right = vr.dot(vb) * k;
    const bottom = vu.dot(va) * k, top = vu.dot(vc) * k;

    const P = new THREE.Matrix4().makePerspective(left, right, top, bottom, near, far);
    // Camera-to-world: the receptor basis, sitting at the source. Note vn points
    // FROM the receptor TOWARD the source, which is the camera's +Z.
    const c2w = new THREE.Matrix4().makeBasis(vr, vu, vn).setPosition(source);
    camera.matrixAutoUpdate = false;
    camera.matrix.copy(c2w);
    camera.updateMatrixWorld(true);
    camera.projectionMatrix.copy(P);
    camera.projectionMatrixInverse.copy(P).invert();

    for (const key of ['A', 'B']) {
      for (const g of groups[key]) {
        g.material.uniforms.uRecD.value = d;
        g.material.uniforms.uRef.value = d;
      }
    }

    // The composite needs the receptor in VIEW space to reconstruct each
    // pixel's ray for the cone cut.
    const w2c = new THREE.Matrix4().copy(c2w).invert();
    const paV = pa.clone().applyMatrix4(w2c);
    const u = composite.uniforms;
    u.uPa.value.copy(paV);
    u.uEdgeR.value.copy(pb.clone().applyMatrix4(w2c).sub(paV));
    u.uEdgeU.value.copy(pc.clone().applyMatrix4(w2c).sub(paV));
    u.uW2C.value.copy(w2c);
    // The march is in WORLD space, not view space: the field is a world-space
    // texture and converting it per sample would be a matrix multiply inside
    // the inner loop for nothing.
    const m = march.uniforms;
    m.uSource.value.copy(source);
    m.uPaW.value.copy(pa);
    m.uEdgeRW.value.copy(pb.clone().sub(pa));
    m.uEdgeUW.value.copy(pc.clone().sub(pa));
    return { d, vr, vu, vn };
  }

  /**
   * The X-ray beam itself, which is NOT the same thing as the receptor.
   *
   * In the bisecting technique the central ray is aimed at the bisector of the
   * tooth axis and the film, so it is not perpendicular to the receptor. When
   * the beam's circular field misses part of the film, that corner records
   * nothing -- the CONE CUT, and one of the errors this is here to teach. It is
   * modelled as what it is: a cone about the beam axis, not a vignette.
   */
  function setBeam({ axis, fieldDiameterMm, distanceMm }) {
    const u = composite.uniforms;
    const axisView = axis.clone().transformDirection(u.uW2C.value).normalize();
    u.uBeamAxis.value.copy(axisView);
    u.uBeamCos.value = Math.cos(Math.atan2(fieldDiameterMm / 2, distanceMm));
  }

  function setEnergy(kvp) {
    const keV = kvp * attenuation.effective_fraction;
    const energies = attenuation.energies_keV;
    let i = 0;
    for (let k = 1; k < energies.length; k++) {
      if (Math.abs(energies[k] - keV) < Math.abs(energies[i] - keV)) i = k;
    }
    const mu = (t) => attenuation.tissues[t].mu_per_mm[i];
    const u = composite.uniforms;
    u.muEnamel.value = mu('enamel');
    u.muDentin.value = mu('dentin');
    u.muPulp.value = mu('pulp');
    u.muZirconia.value = mu('zirconia');
    u.muCortical.value = mu('corticalBone');
    u.muTrabecular.value = mu('trabecularBone');
    u.muPdl.value = mu('pdl');
    u.muGingiva.value = mu('gingiva');
    // THE ONE DERIVED NUMBER IN A MEASURED PIPELINE, and it is worth being
    // explicit about where it comes from.
    //
    // The field is in UNCALIBRATED grey values -- nrrd/volumes.json says so --
    // so nothing in it converts to attenuation on its own. What IS available is
    // a two-point calibration from tissues whose mu is known: cortical and
    // trabecular bone differ by GREY_SEPARATION in this patient's volume
    // (measured: 854.7 vs 631.7 in the isolated bone) and by (muCortical -
    // muTrabecular) in the literature. One grey unit is the ratio.
    //
    // It is therefore anchored rather than tuned, and it rides the kVp control
    // for free because both mu values do. But it IS derived, and the film's
    // provenance must say so.
    u.uMuPerGrey.value = TRABECULAR_GAIN
      * (u.muCortical.value - u.muTrabecular.value) / GREY_SEPARATION;
    u.uShoulder.value = SHOULDER;
    return { keV, tableKeV: energies[i] };
  }

  /**
   * Install the measured trabecular field.
   *
   * `data` is the raw uint8 volume from public/trabecular.bin and `meta` its
   * JSON. Called once; without it the DRR behaves exactly as it did before,
   * which is what makes this safe to ship ahead of the file itself.
   */
  function setField(data, meta) {
    const [dz, dy, dx] = meta.dims_zyx;
    if (data.length !== dx * dy * dz) {
      throw new Error(`DRR: trabecular field is ${data.length} bytes, but `
        + `${meta.dims_zyx.join('x')} needs ${dx * dy * dz}`);
    }
    const tex = new THREE.Data3DTexture(data, dx, dy, dz);
    tex.format = THREE.RedFormat;
    tex.type = THREE.UnsignedByteType;
    // LINEAR, deliberately. The field is already a 0.48 mm sampling of a 0.16 mm
    // measurement; nearest sampling would add a blocky 0.48 mm structure that is
    // not in the anatomy and would read as coarse trabeculae.
    tex.minFilter = tex.magFilter = THREE.LinearFilter;
    tex.wrapS = tex.wrapT = tex.wrapR = THREE.ClampToEdgeWrapping;
    tex.unpackAlignment = 1;
    tex.needsUpdate = true;

    const o = meta.origin_app_mm, st = meta.spacing_mm;
    // A texture coordinate of 0 is the OUTER EDGE of the first texel, while the
    // origin names its CENTRE. Half a voxel out on each side, or every sample is
    // shifted by 0.24 mm and the whole pattern sits off its bone.
    const lo = new THREE.Vector3(o[0] - st / 2, o[1] - st / 2, o[2] - st / 2);
    const hi = new THREE.Vector3(lo.x + dx * st, lo.y + dy * st, lo.z + dz * st);
    const m = march.uniforms;
    m.uField.value = tex;
    m.uFieldMin.value.copy(lo);
    m.uFieldMax.value.copy(hi);
    m.uStep.value = st;
    m.uLsb.value = meta.units_per_lsb;
    m.uZero.value = meta.zero_level;
    field = { meta, tex, lo, hi };
    composite.uniforms.uHasField.value = true;
    return field;
  }

  /**
   * Re-read the anatomy's transforms after something has moved it.
   *
   * The accumulation meshes are frozen copies, which is what makes them cheap;
   * this is the price of that, and it must be called whenever the scene moves
   * or the film will be computed from where the anatomy USED to be.
   */
  function refreshTransforms() {
    for (const [m, src] of sources) {
      src.updateWorldMatrix(true, false);
      m.matrix.copy(src.matrixWorld);
    }
  }

  /** Accumulate both targets. One pass per target, every mesh drawn once. */
  function accumulate() {
    const prevTarget = renderer.getRenderTarget();
    const prevClear = renderer.getClearColor(new THREE.Color());
    const prevAlpha = renderer.getClearAlpha();
    renderer.setClearColor(0x000000, 0);
    for (const [key, rt] of [['A', rtA], ['B', rtB]]) {
      for (const k of ['A', 'B']) {
        for (const g of groups[k]) for (const m of g.members) m.visible = (k === key);
      }
      renderer.setRenderTarget(rt);
      renderer.clear(true, false, false);
      renderer.render(scene, camera);
    }
    if (field) {
      renderer.setRenderTarget(rtT);
      renderer.clear(true, false, false);
      renderer.render(marchScene, quadCam);
    }
    renderer.setRenderTarget(prevTarget);
    renderer.setClearColor(prevClear, prevAlpha);
  }

  /**
   * Choose the display window from the image itself.
   *
   * TAKEN OVER THE METAL-FREE PIXELS, and that is the whole point. The crown
   * reaches an optical depth around 130 while every dental tissue sits between
   * 1 and 5, so a percentile over the whole image is set by the zirconia and
   * crushes the anatomy into the bottom few grey levels. A real sensor does not
   * behave that way either: its range is finite, the restoration saturates, and
   * the tissue around it still uses the full scale.
   */
/**
   * Choose the display window from the image itself.
   *
   * WITH A FIXED LATITUDE THIS IS AN EXPOSURE, NOT A STRETCH.
   *
   * Fitting BOTH ends per film renormalises every image to fill the range, and
   * that is not what a detector does. Measured across all 28 teeth
   * (drr.html?window=1), the fitted width runs 3.95 to 7.19 -- anteriors mean
   * 4.73, posteriors 6.05 -- so an anterior film was being stretched about 1.7x
   * harder than a molar one, and everything faint in it amplified to match.
   * That is what made the trabecular field unreadable on upper anteriors while
   * it was correct on molars.
   *
   * A real detector has ONE latitude and the operator moves the anatomy within
   * it by choosing exposure -- the operator's own description: fewer impulses
   * for anteriors, more for posteriors. So the width is fixed and only the
   * offset is fitted, which is the same two numbers standing for the right two
   * things: the hardware, and a choice.
   *
   * `latitude` null keeps the old both-ends behaviour, because the harness
   * needs to be able to show what changed.
   */
  function autoWindow({ low = 2, high = 99.5, metalCut = 20,
                        latitude = LATITUDE } = {}) {
    composite.uniforms.uTauOut.value = true;
    const prev = renderer.getRenderTarget();
    renderer.setRenderTarget(rtTau);
    renderer.render(quadScene, quadCam);
    const w = rtTau.width, h = rtTau.height;
    const buf = tauFloat ? new Float32Array(w * h * 4) : new Uint16Array(w * h * 4);
    try {
      renderer.readRenderTargetPixels(rtTau, 0, 0, w, h, buf);
    } catch (err) {
      composite.uniforms.uTauOut.value = false;
      renderer.setRenderTarget(prev);
      return null;
    }
    renderer.setRenderTarget(prev);
    composite.uniforms.uTauOut.value = false;

    const vals = [];
    for (let i = 0; i < w * h; i++) {
      const t = tauFloat ? buf[i * 4] : halfToFloat(buf[i * 4]);
      if (Number.isFinite(t) && t < metalCut) vals.push(t);
    }
    if (vals.length < 16) return null;   // caller must SAY SO, not paper over it
    vals.sort((a, b) => a - b);
    const at = (p) => vals[Math.min(vals.length - 1,
      Math.max(0, Math.round((p / 100) * (vals.length - 1))))];
    const lo = at(low);
    const hi = latitude ? lo + latitude : at(high);
    composite.uniforms.uLo.value = lo;
    composite.uniforms.uHi.value = hi;
    return { lo, hi, fitted: at(high), sampled: vals.length, of: w * h };
  }

  // Output to an 8-bit target so the result can be read back into a 2D canvas.
  // The atlas hosts the film in a side panel; giving that panel its own WebGL
  // context would upload all 15 MB of geometry a second time, and the film only
  // changes when a control does, so one readback per change is far cheaper than
  // a second copy of the mouth.
  const rtOut = new THREE.WebGLRenderTarget(2, 2, {
    type: THREE.UnsignedByteType, format: THREE.RGBAFormat,
    depthBuffer: false, stencilBuffer: false,
  });

  function toCanvas(ctx, w, h) {
    rtOut.setSize(w, h);
    const prev = renderer.getRenderTarget();
    renderer.setRenderTarget(rtOut);
    renderer.render(quadScene, quadCam);
    const buf = new Uint8Array(w * h * 4);
    renderer.readRenderTargetPixels(rtOut, 0, 0, w, h, buf);
    renderer.setRenderTarget(prev);
    const img = ctx.createImageData(w, h);
    // GL reads bottom-up; a film that is upside down is not a small error here.
    for (let y = 0; y < h; y++) {
      const src = (h - 1 - y) * w * 4;
      img.data.set(buf.subarray(src, src + w * 4), y * w * 4);
    }
    ctx.putImageData(img, 0, 0);
  }

  function draw(targetOrNull = null) {
    const prev = renderer.getRenderTarget();
    renderer.setRenderTarget(targetOrNull);
    renderer.render(quadScene, quadCam);
    renderer.setRenderTarget(prev);
  }

  return {
    ok: true, caps, camera, build, resize, place, setBeam, setEnergy,
    accumulate, autoWindow, draw, toCanvas, setField, refreshTransforms,
    hasField: () => !!field,
    setGamma: (g) => { composite.uniforms.uGamma.value = g; },
    /**
     * Set the display window without reading the film.
     *
     * THE EXPOSURE IS CHOSEN BEFORE THE BUTTON IS PRESSED. `autoWindow` reads
     * back the tau target and picks the window from it, and it was called from
     * `update()` -- so every slider move re-derived a number that never
     * changes, at the cost of a full GPU readback per render. That readback is
     * also the one thing here that can FAIL on a weak GPU, and when it did the
     * film reported itself uncalibrated; a constant cannot fail.
     *
     * `autoWindow` stays, because drr.html?window=1 exists to measure exactly
     * this and would have nothing to measure without it.
     */
    setWindow: (lo = WINDOW_LO, latitude = LATITUDE) => {
      composite.uniforms.uLo.value = lo;
      composite.uniforms.uHi.value = lo + latitude;
      return { lo, hi: lo + latitude, fixed: true };
    },
    window: () => ({ lo: composite.uniforms.uLo.value, hi: composite.uniforms.uHi.value }),
  };
}
