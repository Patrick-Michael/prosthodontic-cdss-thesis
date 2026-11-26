// Pure mesh geometry, shared by the asset build and the tests that guard it.
//
// Split out of build-assets.mjs when the DRR work began. The DRR integrates
// path length through each structure as (back-face depths - front-face depths),
// which asks two things of every mesh that the 3D view never did: that it be
// CLOSED, and that it be wound OUTWARD. Both are cheap to check and silent when
// wrong, so they belong somewhere a test can reach them.

/** Parse a binary STL into a flat, non-indexed Float32Array of positions. */
export function parseBinarySTL(buf) {
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const triangles = view.getUint32(80, true);
  const expected = 84 + triangles * 50;
  if (buf.byteLength < expected) {
    throw new Error(`truncated STL: header claims ${triangles} triangles (${expected} bytes), file is ${buf.byteLength}`);
  }
  const positions = new Float32Array(triangles * 9);
  let o = 84;
  for (let t = 0; t < triangles; t++) {
    o += 12; // skip the per-facet normal; we recompute normals anyway
    for (let v = 0; v < 9; v++) {
      positions[t * 9 + v] = view.getFloat32(o, true);
      o += 4;
    }
    o += 2; // attribute byte count
  }
  return positions;
}

/**
 * Merge bitwise-identical vertices into an indexed mesh.
 * Keyed on the raw float bits so no coordinate is ever rounded — welding must
 * not soften cusp tips or occlusal fissures.
 */
export function weldExact(positions) {
  const bits = new Uint32Array(positions.buffer, positions.byteOffset, positions.length);
  const seen = new Map();
  const out = [];
  const wide = new Uint32Array(positions.length / 3);

  for (let i = 0, n = positions.length / 3; i < n; i++) {
    const key = `${bits[i * 3]},${bits[i * 3 + 1]},${bits[i * 3 + 2]}`;
    let idx = seen.get(key);
    if (idx === undefined) {
      idx = out.length / 3;
      seen.set(key, idx);
      out.push(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);
    }
    wide[i] = idx;
  }

  // Indices are the single largest thing in the buffer — bigger than positions
  // and normals combined at 32 bits. Every structure here welds to well under
  // 65536 vertices, so 16-bit indices halve that for free.
  const vertexCount = out.length / 3;
  const indices = vertexCount <= 0xffff ? Uint16Array.from(wide) : wide;

  return { positions: new Float32Array(out), indices };
}

/**
 * Is this surface closed? Counts how many faces use each edge; a closed surface
 * uses every edge exactly twice.
 *
 * Non-manifold edges (three or more faces) do NOT make a surface open and are
 * not counted here: they are harmless to ray integration, while HOLES are not.
 * The DRR integrates path length as (back-face depths - front-face depths),
 * which is only meaningful if every ray that enters a solid also leaves it.
 */
export function boundaryEdges(indices) {
  const use = new Map();
  for (let i = 0; i < indices.length; i += 3) {
    for (const [a, b] of [[0, 1], [1, 2], [2, 0]]) {
      const u = indices[i + a], v = indices[i + b];
      const key = u < v ? `${u},${v}` : `${v},${u}`;
      use.set(key, (use.get(key) || 0) + 1);
    }
  }
  let open = 0;
  for (const n of use.values()) if (n === 1) open++;
  return open;
}

/** Signed volume by the divergence theorem. Negative means inward winding. */
export function signedVolume(positions, indices) {
  let v = 0;
  for (let i = 0; i < indices.length; i += 3) {
    const a = indices[i] * 3, b = indices[i + 1] * 3, c = indices[i + 2] * 3;
    const ax = positions[a], ay = positions[a + 1], az = positions[a + 2];
    const bx = positions[b], by = positions[b + 1], bz = positions[b + 2];
    const cx = positions[c], cy = positions[c + 1], cz = positions[c + 2];
    v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);
  }
  return v / 6;
}

/** Reverse triangle winding in place. */
export function flipWinding(indices) {
  for (let i = 0; i < indices.length; i += 3) {
    const t = indices[i + 1];
    indices[i + 1] = indices[i + 2];
    indices[i + 2] = t;
  }
}

/**
 * Euler characteristic, component count and genus of a closed surface.
 *
 * WHY THIS EXISTS. `boundaryEdges` returns 0 for a surface with a TUNNEL
 * through it: a torus is every bit as closed as a sphere. So "closed" and "no
 * holes" are different claims, and the closedness check cannot tell them apart.
 * The operator found a tunnel clean through the distolingual cusp of the crown
 * on 19 by looking at it, after that mesh had passed every check here.
 *
 * chi = V - E + F. For c disjoint closed surfaces of total genus g,
 * chi = 2c - 2g, so genus = c - chi/2.
 *
 * A high genus is NOT automatically a defect -- the mandible carries its own
 * canal, and a structure meshed as two branches is two spheres, not one. It is
 * a defect where the object is known to be a simple solid.
 */
export function topology(positions, indices) {
  const V = positions.length / 3;
  const F = indices.length / 3;
  const edges = new Set();
  const parent = new Int32Array(V);
  for (let i = 0; i < V; i++) parent[i] = i;
  const find = (x) => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
  for (let i = 0; i < indices.length; i += 3) {
    for (const [a, b] of [[0, 1], [1, 2], [2, 0]]) {
      const u = indices[i + a], v = indices[i + b];
      edges.add(u < v ? u * V + v : v * V + u);
      const ru = find(u), rv = find(v);
      if (ru !== rv) parent[ru] = rv;
    }
  }
  const roots = new Set();
  for (let i = 0; i < V; i++) roots.add(find(i));
  const E = edges.size;
  const chi = V - E + F;
  const components = roots.size;
  return { V, E, F, chi, components, genus: components - chi / 2 };
}
