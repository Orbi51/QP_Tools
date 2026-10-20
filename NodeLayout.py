"""Cluster Layout: lays a node tree out in framed functional clusters.

Each geometry (or shader) step sits with the field nodes that feed it in a compact block; blocks follow the flow
left to right with wider gaps, each in a labelled frame. A big block made of several steps (typically a kept
frame) is laid out the same way inside, its steps in nested sub-frames; other big blocks are split into the parts
that each feed one node. Every link goes left to right; links that skip columns get reroutes so they never
run behind nodes. Existing frames are kept as clusters (Keep Frames), existing reroutes are replaced, so running
it again gives the same result. Each cluster gets its own Group Input showing only the sockets it uses.
Works on geometry, shader and other node trees.
"""
import sys
import time

import bpy
from bpy.props import BoolProperty, EnumProperty
from bpy.types import Operator

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

GAP_X, GAP_Y = 40, 24            # inside a cluster
CL_GAP_X, CL_GAP_Y = 180, 120    # between clusters
MIN_CLUSTER = 4
FRAME_TOP, SUB_FRAME_TOP = 30.0, 38.0   # frame top above its top nodes; extra when the top row is a sub-frame (5.2)
LANE_GAP = 26.0                        # lane above the frame / lane under it
MAX_MERGED = 14
FLOW_TYPES = {'GEOMETRY', 'SHADER'}
SOCK_Y0, SOCK_DY = 33.5, 20.6    # first output socket below the node top, spacing (view units, measured in 5.2)
_SCALE = [1.0]                   # node.dimensions / view units (the UI scale), set per tree by _measure_scale


def _measure_scale(tree):
    r = sorted(n.dimensions[0] / n.width for n in tree.nodes
               if n.bl_idname not in ('NodeReroute', 'NodeFrame') and not n.hide and n.width > 1 and n.dimensions[0] > 1)
    _SCALE[0] = r[len(r) // 2] if r else 1.0


def _out_y(n, ident):
    """Distance from the node top to the output socket `ident` (outputs are drawn first, under the header)."""
    if n.bl_idname == 'NodeReroute':
        return 0.0
    if n.hide:
        return 12.0
    vis = [o for o in n.outputs if o.enabled and not o.hide]
    i = next((j for j, o in enumerate(vis) if o.identifier == ident), 0)
    return SOCK_Y0 + SOCK_DY * i


def _h(n):
    if getattr(n, "dimensions", None) and n.dimensions[1] > 1:
        return n.dimensions[1] / _SCALE[0]
    if n.bl_idname == 'NodeReroute':
        return 20
    rows = sum(1 for s in n.outputs if s.enabled and not s.hide)
    for s in n.inputs:
        if not s.enabled or s.hide:
            continue
        rows += 1
        if not s.is_linked and s.type == 'VECTOR' and not s.hide_value:
            rows += 2
    props = 1 if any(p in n.bl_rna.properties for p in ("data_type", "operation", "domain", "mode")) else 0
    return 36 + 22 * (rows + props)


def _w(n):
    if n.bl_idname == 'NodeReroute':
        return 20
    if getattr(n, "dimensions", None) and n.dimensions[0] > 1:
        return n.dimensions[0] / _SCALE[0]
    return n.width


def _graph(tree, only=None):
    nodes = [n for n in tree.nodes if n.bl_idname != 'NodeFrame' and (only is None or n.name in only)]
    names = {n.name for n in nodes}
    preds = {k: set() for k in names}
    succs = {k: set() for k in names}
    for l in tree.links:
        a, b = l.from_node.name, l.to_node.name
        if a in names and b in names and a != b and not l.is_muted:
            preds[b].add(a)
            succs[a].add(b)
    order, seen = [], set()

    def visit(k):
        if k in seen:
            return
        seen.add(k)
        for p in sorted(preds[k]):
            visit(p)
        order.append(k)
    for n in nodes:
        visit(n.name)
    return nodes, preds, succs, order


def _is_flow(n):
    if n.bl_idname in ('NodeGroupInput', 'NodeGroupOutput'):
        return True
    return any(s.type in FLOW_TYPES for s in list(n.inputs) + list(n.outputs) if s.enabled)


def _size(tree, names):
    """Node count without the Group Inputs: the layout makes one per cluster, so counting them would make the
    second run cluster differently from the first."""
    return sum(1 for k in names if tree.nodes[k].bl_idname != 'NodeGroupInput')


def _set_loc(n, x, y):
    if hasattr(n, "location_absolute"):
        n.location_absolute = (x, y)
    else:
        n.location = (x, y)


def _abs_loc(n):
    loc = n.location_absolute if hasattr(n, "location_absolute") else n.location
    return loc[0], loc[1]


def _corner(tree, names):
    """Top-left corner (min x, max y) of the named nodes."""
    pts = [_abs_loc(tree.nodes[k]) for k in names if tree.nodes[k].bl_idname != 'NodeFrame']
    return min(p[0] for p in pts), max(p[1] for p in pts)


def _type_label(n):
    if n.bl_idname == 'GeometryNodeStoreNamedAttribute' and not n.inputs["Name"].is_linked             and n.inputs["Name"].default_value:
        return f"Store {n.inputs['Name'].default_value}"
    if getattr(n, "node_tree", None):
        return n.node_tree.name.lstrip(".")
    return n.bl_label


def _relink(tree, link, new_from):
    """Move `link` to start at `new_from`. Removes the old link first: on a multi-input socket (Join Geometry...)
    links.new() ADDS a link instead of replacing it, which would duplicate the connection."""
    dst = link.to_socket
    tree.links.remove(link)
    return tree.links.new(new_from, dst)


def _label(tree, members, key=None):
    """Frame name: the main node's own label, else the most downstream labelled node, else the main node's type."""
    io = ('NodeGroupInput', 'NodeGroupOutput')
    flow = [k for k in members if _is_flow(tree.nodes[k]) and tree.nodes[k].bl_idname not in io]
    main = key if key in members and tree.nodes[key].bl_idname not in io else (flow[-1] if flow else members[-1])
    if tree.nodes[main].label:
        return tree.nodes[main].label
    labelled = [k for k in members if tree.nodes[k].label and tree.nodes[k].bl_idname not in io]
    if labelled:
        return tree.nodes[labelled[-1]].label
    return _type_label(tree.nodes[main])


def _merge_cycles(cl, succs):
    """Clusters that feed each other (only possible with hand-made frames) can't be laid out left to right: each
    such cycle (strongly connected component of the cluster graph) becomes one cluster, named after its biggest
    member. The sub-cluster split then rebuilds the parts inside it."""
    g = {c: set() for c in set(cl.values())}
    for k, ss in succs.items():
        for s_ in ss:
            if k in cl and s_ in cl and cl[s_] != cl[k]:
                g[cl[k]].add(cl[s_])
    index, low, on, st, comp, i = {}, {}, set(), [], {}, 0
    for root in sorted(g):                            # iterative Tarjan
        if root in index:
            continue
        index[root] = low[root] = i
        i += 1
        st.append(root)
        on.add(root)
        work = [(root, iter(sorted(g[root])))]
        while work:
            v, it = work[-1]
            w = next(it, None)
            if w is not None:
                if w not in index:
                    index[w] = low[w] = i
                    i += 1
                    st.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(g[w]))))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                scc = []
                while True:
                    x = st.pop()
                    on.discard(x)
                    scc.append(x)
                    if x == v:
                        break
                if len(scc) > 1:
                    for x in scc:
                        comp[x] = scc
    if comp:
        size = {}
        for c in cl.values():
            size[c] = size.get(c, 0) + 1
        best = {c: max(comp[c], key=lambda c_: (size[c_], c_)) for c in comp}
        for k in cl:
            if cl[k] in best:
                cl[k] = best[cl[k]]


def auto_clusters(tree, only=None):
    """[(label, [node names])] in flow order."""
    nodes, preds, succs, order = _graph(tree, only)
    pos = {k: i for i, k in enumerate(order)}
    framed = {}
    for n in nodes:                                   # nested frames count as their outermost frame (the layout
        f = n.parent                                  # makes its own sub-frames again; as clusters of their own
        while f is not None and f.parent is not None:  # they would cycle with the rest of their parent)
            f = f.parent
        if f is not None:
            framed.setdefault(f.name, []).append(n.name)
    cl = {}                                           # node -> cluster key
    if framed:
        for f, ms in framed.items():
            for k in ms:
                cl[k] = "F:" + f
    seeds = [k for k in order if k not in cl and _is_flow(tree.nodes[k]) and tree.nodes[k].bl_idname != 'NodeGroupInput']
    for k in seeds:
        cl[k] = k
    cpos = {k: pos[k] for k in seeds}
    for f, ms in framed.items():
        cpos["F:" + f] = min(pos[k] for k in ms)
    # field nodes (and Group Input nodes) join the first flow consumer they feed
    for k in reversed(order):
        if k in cl:
            continue
        tgt = [cl[s] for s in succs[k] if s in cl]
        if tgt:
            cl[k] = min(tgt, key=lambda c: cpos.get(c, 0))
        else:
            cl[k] = k
            cpos[k] = pos[k]
    _merge_cycles(cl, succs)
    # merge tiny clusters along straight geometry chains (in the order of their first node that is not a Group Input:
    # the layout splits those, so they would change the merge order on the next run)
    members = {}
    for gi in (False, True):
        for k in order:
            if (tree.nodes[k].bl_idname == 'NodeGroupInput') == gi:
                members.setdefault(cl[k], []).append(k)
    changed = True
    while changed:
        changed = False
        for c in list(members):
            if c.startswith("F:") or c not in members or _size(tree, members[c]) >= MIN_CLUSTER:
                continue
            nxt = {cl[s] for k in members[c] for s in succs[k]} - {c}
            prv = {cl[p] for k in members[c] for p in preds[k]} - {c}
            if len(nxt) == 1:
                t = next(iter(nxt))
                if not t.startswith("F:") and _size(tree, members[t]) + _size(tree, members[c]) <= MAX_MERGED:
                    for k in members[c]:
                        cl[k] = t
                    members[t] = members[c] + members[t]
                    del members[c]
                    changed = True
                    continue
            if len(prv) == 1:
                t = next(iter(prv))
                if not t.startswith("F:") and _size(tree, members[t]) + _size(tree, members[c]) <= MAX_MERGED:
                    for k in members[c]:
                        cl[k] = t
                    members[t] += members[c]
                    del members[c]
                    changed = True
    out = []
    for c, ms in sorted(members.items(), key=lambda kv: min(pos[k] for k in kv[1])):
        lab = tree.nodes[c[2:]].label if c.startswith("F:") and tree.nodes[c[2:]].label else _label(tree, ms, c)
        out.append((lab, ms))
    return out


SUB_MIN = 14          # clusters bigger than this are split into sub-clusters (nested frames)
SUB_GAP_X, SUB_GAP_Y = 90, 60


def _postdom_groups(tree, ms, preds, succs):
    """Split a cluster into the parts that each feed ONE node (post-dominator subtrees), e.g. the per-slot chains
    of a repeated computation. Returns [[names]] in dependency order, or [] when nothing is worth splitting."""
    S = set(ms)
    order = list(ms)
    VS = "__sink__"
    succ_in = {k: [s for s in succs[k] if s in S] or [VS] for k in order}
    ipdom = {VS: VS}
    rpo = list(reversed(order))                       # consumers first
    idx = {VS: -1}
    for i, k in enumerate(rpo):
        idx[k] = i

    def inter(x, y):
        while x != y:
            while idx[x] > idx[y]:
                x = ipdom[x]
            while idx[y] > idx[x]:
                y = ipdom[y]
        return x
    changed = True
    while changed:
        changed = False
        for k in rpo:
            ss = [s for s in succ_in[k] if s in ipdom]
            if not ss:
                continue
            new = ss[0]
            for s in ss[1:]:
                new = inter(new, s)
            if ipdom.get(k) != new:
                ipdom[k] = new
                changed = True
    kids = {}
    for k in order:
        kids.setdefault(ipdom.get(k, VS), []).append(k)

    def subtree(k):
        out, st = [], [k]
        while st:
            x = st.pop()
            out.append(x)
            st += kids.get(x, [])
        return out
    groups, taken = [], set()

    def pick(root):
        for c in kids.get(root, []):
            t = subtree(c)
            if 3 <= _size(tree, t) <= SUB_MIN:
                groups.append(t)
                taken.update(t)
            elif _size(tree, t) > SUB_MIN:
                pick(c)
    pick(VS)
    if len(groups) < 2:
        return []
    pos = {k: i for i, k in enumerate(order)}
    out = [sorted(g, key=lambda k: pos[k]) for g in groups]
    # the remaining nodes are NOT returned as a group: they stay individual nodes between the sub-clusters
    # (as one block they would both feed and consume sub-clusters -> backward links)
    return sorted(out, key=lambda g: max(pos[k] for k in g))


def _add_reroutes(tree, ms, col, preds, succs):
    """Links that skip columns inside a block get a reroute per crossed column, so they never pass behind nodes.
    Returns [(source node, source socket identifier, [(column, reroute name)])] and rebuilds preds / succs for
    the block."""
    S = set(ms)
    chains = {}
    for l in list(tree.links):
        a, b_ = l.from_node.name, l.to_node.name
        if a not in S or b_ not in S or col[b_] - col[a] <= 1:
            continue
        chain = chains.setdefault((a, l.from_socket.identifier), {})
        prev = l.from_socket
        for c in range(col[a] + 1, col[b_]):
            if c not in chain:
                r = tree.nodes.new("NodeReroute")
                tree.links.new(prev, r.inputs[0])
                chain[c] = r
            prev = chain[c].outputs[0]
        _relink(tree, l, prev)
    out = [(a, sid, sorted((c, r.name) for c, r in chain.items())) for (a, sid), chain in chains.items()]
    names = S | {r for _, _, rs in out for _, r in rs}
    for k in names:                                    # keep links to nodes outside the block
        preds[k] = {q for q in preds.get(k, ()) if q not in names}
        succs[k] = {q for q in succs.get(k, ()) if q not in names}
    for l in tree.links:
        a, b_ = l.from_node.name, l.to_node.name
        if a in names and b_ in names:
            preds[b_].add(a)
            succs[a].add(b_)
    return out


def _entry_chain(tree, order, S, preds):
    """Flow nodes fed from outside S, or from such a node: the chain that enters the block. They keep the leftmost
    column they can take; everything else (fields, Group Inputs, Object Info, chains that start inside the
    block) can move right to sit next to its consumer."""
    fixed = set()
    for k in order:
        if _is_flow(tree.nodes[k]) and any(p not in S or p in fixed for p in preds[k]):
            fixed.add(k)
    return fixed


def _layout_block(tree, ms, preds, succs, reroutes=True):
    """Lay out one cluster at the origin; returns (locations, width, height)."""
    S = set(ms)
    col = {}
    order = [k for k in ms]                                   # ms is already topological
    for k in order:
        col[k] = 1 + max((col[p] for p in preds[k] if p in S), default=-1)
    last = max(col.values(), default=0)
    fixed = _entry_chain(tree, order, S, preds)
    for k in reversed(order):                                  # pull the rest right, toward their consumer
        if k in fixed:
            continue
        inside = [col[s] for s in succs[k] if s in S]
        if inside:
            col[k] = max(col[k], min(inside) - 1)
    cols = [[] for _ in range(last + 1)]
    for k in order:
        cols[col[k]].append(k)
    rank = {k: (0 if _is_flow(tree.nodes[k]) else 1, i) for c in cols for i, k in enumerate(c)}
    for _ in range(4):
        for c in cols:
            for k in c:
                nb = [rank[o][1] for o in list(preds[k]) + list(succs[k]) if o in S]
                if nb:
                    rank[k] = (rank[k][0], sum(nb) / len(nb))
            c.sort(key=lambda k: rank[k])
            for i, k in enumerate(c):
                rank[k] = (rank[k][0], float(i))
    chains = _add_reroutes(tree, order, col, preds, succs) if reroutes else []
    rcols = {c for _, _, rs in chains for c, _ in rs}
    x, H = 0.0, 0.0
    loc, colx, colw, occ = {}, [], [], []
    for ci, c in enumerate(cols):
        w = max((_w(tree.nodes[k]) for k in c), default=20.0 if ci in rcols else 0.0)
        colx.append(x)
        colw.append(w)
        occ.append([])
        if not w:
            continue
        y = 0.0
        for k in c:
            loc[k] = (x, y)
            h = _h(tree.nodes[k])
            occ[ci].append((y - h, y))
            y -= h + GAP_Y
        H = max(H, -y)
        x += w + GAP_X

    # a chain runs straight at the height of its source socket, or at the nearest height that is free in every
    # column it crosses (one bend down at the start instead of a zigzag)
    def free(y, cs):
        return all(not (lo - 14 < y < hi + 14) for c in cs for lo, hi in occ[c])

    def src_y(ch):
        return min(loc[ch[0]][1] - _out_y(tree.nodes[ch[0]], ch[1]), -10.0)

    def tgt_key(ch):                         # chains that must bend take rows in the order of their targets
        ls = tree.nodes[ch[2][-1][1]].outputs[0].links
        if not ls or ls[0].to_node.name not in loc:
            return (0.0, 0)
        t = ls[0].to_socket
        vis = [i for i in t.node.inputs if i.enabled and not i.hide]
        return (-loc[t.node.name][1], vis.index(t) if t in vis else 0)

    def place(ch, y):
        for c, r in ch[2]:
            loc[r] = (colx[c] + colw[c] * 0.5, y)
            occ[c].append((y - 4, y + 4))
    bent = []
    for ch in sorted(chains, key=lambda ch: -src_y(ch)):
        if free(src_y(ch), [c for c, _ in ch[2]]):
            place(ch, src_y(ch))
        else:
            bent.append(ch)
    for ch in sorted(bent, key=tgt_key):
        cs = [c for c, _ in ch[2]]
        y0 = y = src_y(ch)
        for i in range(1, 400):
            if free(y, cs):
                break
            d = 11.0 * ((i + 1) // 2) * (1 if i % 2 else -1)
            y = min(y0 - d, -10.0)
        place(ch, y)
    for ch in chains:
        H = max(H, -loc[ch[2][0][1]][1] + 20)
    return loc, max(x - GAP_X, 0.0), H


def _split_group_inputs(tree, groups):
    """One Group Input per group (list of node names), showing only the sockets that group uses.
    Returns the groups with the new Group Input nodes added."""
    gid = {k: i for i, g in enumerate(groups) for k in g}
    for gi in [tree.nodes[k] for g in groups for k in g if tree.nodes[k].bl_idname == 'NodeGroupInput']:
        by_g = {}
        for l in list(tree.links):
            if l.from_node == gi and l.to_node.name in gid:
                by_g.setdefault(gid[l.to_node.name], []).append(l)
        if len(by_g) <= 1:
            continue
        home = gid.get(gi.name)
        for g_i, ls in by_g.items():
            if g_i == home:
                continue
            ng = tree.nodes.new("NodeGroupInput")
            used = set()
            for l in ls:
                fid = l.from_socket.identifier
                _relink(tree, l, next(o for o in ng.outputs if o.identifier == fid))
                used.add(fid)
            for o in ng.outputs:
                o.hide = bool(o.identifier) and o.identifier not in used
            groups[g_i].insert(0, ng.name)
            gid[ng.name] = g_i
        for o in gi.outputs:
            o.hide = bool(o.identifier) and not o.is_linked
    return groups


def _refresh_graph(tree, ms, preds, succs, only):
    """Rebuild preds / succs in place after Group Inputs were split; returns the new topological positions."""
    if only is not None:
        only.update(ms)                                # the new Group Inputs belong to the laid-out nodes
    nodes_, preds2, succs2, order_ = _graph(tree, only)
    for k in nodes_:
        preds.setdefault(k.name, set())
        succs.setdefault(k.name, set())
    for k, v in preds2.items():
        preds[k] = v
    for k, v in succs2.items():
        succs[k] = v
    return {k: i for i, k in enumerate(order_)}


def _layout_steps(tree, steps, preds, succs, only, frames):
    """A big cluster laid out like a tree of its own: each step [(label, names)] in its own sub-frame, the steps in
    columns along the cluster's main chain, with lanes for the links that skip steps."""
    groups = _split_group_inputs(tree, [list(g) for _, g in steps])
    po = _refresh_graph(tree, [k for g in groups for k in g], preds, succs, only)
    steps = [(lab, sorted(g, key=lambda k: po[k])) for (lab, _), g in zip(steps, groups)]
    flow = [k for g in groups for k in g if _is_flow(tree.nodes[k]) and tree.nodes[k].bl_idname != 'NodeGroupInput']
    sink = max(flow, key=lambda k: po[k]) if flow else None
    loc, w, h, specs, _, _ = _arrange(tree, steps, preds, succs, po, only, frames, SUB_GAP_X, SUB_GAP_Y + 30, sink)
    top = max((y for _, y in loc.values()), default=0.0)
    if top > 0:                                        # lanes run above the steps: the cluster starts at the top lane
        loc = {k: (x, y - top) for k, (x, y) in loc.items()}
        h += top
    return loc, w, h, specs


def _layout_region(tree, ms, preds, succs, only=None, frames=True):
    """A cluster: one block, or (when big) a nested layout. A big cluster made of several steps (typically a kept
    frame) is laid out like a tree of its own (_layout_steps); otherwise each sub-cluster (post-dominator subtree)
    is one big item among the remaining nodes, in its own nested frame. Every link still goes left to right.
    Returns (locations, width, height, [(sub-frame label, member names, nested sub-frames)])."""
    if _size(tree, ms) > SUB_MIN:
        steps = auto_clusters(tree, set(ms))
        if sum(1 for _, g in steps if _size(tree, g) >= 3) >= 2:
            return _layout_steps(tree, steps, preds, succs, only, frames)
    subs = _postdom_groups(tree, ms, preds, succs) if _size(tree, ms) > SUB_MIN else []
    subs = [g for g in subs if _size(tree, g) >= 3 and len(g) < len(ms)]
    if len(subs) < 2:
        loc, w, h = _layout_block(tree, ms, preds, succs)
        return loc, w, h, []
    rest_ = [k for k in ms if not any(k in g for g in subs)]
    groups_ = _split_group_inputs(tree, [list(g) for g in subs] + [rest_])
    subs, rest_ = groups_[:-1], groups_[-1]
    ms = [k for g in groups_ for k in g]
    po = _refresh_graph(tree, ms, preds, succs, only)
    subs = [sorted(g, key=lambda k: po[k]) for g in subs]
    ms = sorted(ms, key=lambda k: po[k])
    S = set(ms)
    item_of = {}
    for i, g in enumerate(subs):
        for k in g:
            item_of[k] = ("g", i)
    for k in ms:
        item_of.setdefault(k, ("n", k))
    blocks = {("g", i): _layout_block(tree, g, preds, succs) for i, g in enumerate(subs)}
    for it, (bl, _, _) in blocks.items():             # reroutes made inside a sub-cluster belong to it
        for k in bl:
            item_of.setdefault(k, it)
    items = list(dict.fromkeys(item_of[k] for k in ms))
    ip = {it: set() for it in items}
    for k in list(item_of):
        for pk in preds.get(k, ()):
            if pk in item_of and item_of[pk] != item_of[k]:
                ip[item_of[k]].add(item_of[pk])
    # longest-path columns over the contracted graph (Kahn; ms is topological so cycles cannot occur)
    col, done, topo = {}, set(), []
    while len(done) < len(items):
        ready = [it for it in items if it not in done and not (ip[it] - done)]
        if not ready:
            ready = [next(it for it in items if it not in done)]
        for it in ready:
            col[it] = 1 + max((col[q] for q in ip[it] if q in col), default=-1)
            done.add(it)
            topo.append(it)
    # pull the items off the entry chain right, toward their consumer (as in _layout_block)
    fixed = _entry_chain(tree, ms, S, preds)
    isucc = {it: set() for it in items}
    for it, ps in ip.items():
        for q in ps:
            isucc[q].add(it)
    for it in reversed(topo):
        if any(k in fixed for k in ([it[1]] if it[0] == "n" else subs[it[1]])):
            continue
        if isucc[it]:
            col[it] = max(col[it], min(col[s] for s in isucc[it]) - 1)

    def size(it):
        if it[0] == "g":
            return blocks[it][1], blocks[it][2]
        n = tree.nodes[it[1]]
        return _w(n), _h(n)
    ncol = max(col.values()) + 1
    colw = [0.0] * ncol
    for it in items:
        colw[col[it]] = max(colw[col[it]], size(it)[0])
    xs, x = [], 0.0
    for c in range(ncol):
        xs.append(x)
        x += colw[c] + SUB_GAP_X
    loc, ys, nested, H = {}, {}, [], 0.0
    for it in items:
        c = col[it]
        y = ys.get(c, 0.0)
        w_, h_ = size(it)
        if it[0] == "g":
            for k, (lx, ly) in blocks[it][0].items():
                loc[k] = (xs[c] + lx, y + ly)
            nested.append((_label(tree, subs[it[1]], subs[it[1]][-1]), list(blocks[it][0]), []))
            ys[c] = y - h_ - SUB_GAP_Y - 30
        else:
            loc[it[1]] = (xs[c], y)
            ys[c] = y - h_ - GAP_Y
        H = max(H, -ys[c])
    return loc, max(x - SUB_GAP_X, 0.0), H, nested


def _dissolve_reroutes(tree, only=None):
    """Replace every reroute chain by direct links (planned first by names / identifiers, then applied)."""
    rr = {n.name for n in tree.nodes if n.bl_idname == 'NodeReroute' and (only is None or n.name in only)}
    if not rr:
        return

    def source(sock):                        # real output socket feeding `sock` through reroutes
        while sock.links:
            fs = sock.links[0].from_socket
            if fs.node.name in rr:
                sock = fs.node.inputs[0]
                continue
            return fs
        return None
    plan = set()
    for n in tree.nodes:
        if n.name in rr:
            continue
        for s_ in n.inputs:
            for l in s_.links:
                if l.from_node.name in rr:
                    src = source(l.from_node.inputs[0])
                    if src is not None:
                        plan.add((src.node.name, src.identifier, n.name, s_.identifier))
    for nm_ in rr:
        tree.nodes.remove(tree.nodes[nm_])
    for fn, fi, tn, ti in plan:
        fs = next(o for o in tree.nodes[fn].outputs if o.identifier == fi)
        ts = next(i for i in tree.nodes[tn].inputs if i.identifier == ti)
        tree.links.new(fs, ts)


def _thin_reroutes(tree, only=None):
    """Remove the reroutes in the middle of a straight row: a reroute at the height of what feeds it, feeding only
    reroutes on the same row, adds nothing (only the ones where the line bends are kept)."""
    def y_of(n):
        return n.location_absolute.y if hasattr(n, "location_absolute") else n.location.y
    changed = True
    while changed:
        changed = False
        for nm in [n.name for n in tree.nodes if n.bl_idname == 'NodeReroute' and (only is None or n.name in only)]:
            r = tree.nodes.get(nm)
            if r is None or len(r.inputs[0].links) != 1 or not r.outputs[0].links:
                continue
            src = r.inputs[0].links[0].from_socket
            y = y_of(r)
            sy = y_of(src.node) - _out_y(src.node, src.identifier)
            outs = r.outputs[0].links
            if abs(sy - y) > 1 or any(l.to_node.bl_idname != 'NodeReroute' or abs(y_of(l.to_node) - y) > 1 for l in outs):
                continue
            fn, fi = src.node.name, src.identifier          # by name: socket references go stale on removal
            dsts = [l.to_node.name for l in outs]
            tree.nodes.remove(r)
            fs = next(o for o in tree.nodes[fn].outputs if o.identifier == fi)
            for d in dsts:
                tree.links.new(fs, tree.nodes[d].inputs[0])
            changed = True


def _drop_frames(tree, only=None):
    """Remove the frames (only=None), or take the `only` nodes out of their frames and remove the frames left empty."""
    touched = set()
    if only is not None:
        for n in tree.nodes:
            if n.name in only and n.bl_idname != 'NodeFrame':
                f = n.parent
                while f is not None:
                    touched.add(f.name)
                    f = f.parent
                n.parent = None
    while True:
        empty = [f for f in tree.nodes if f.bl_idname == 'NodeFrame'
                 and (only is None or (f.name in touched and not any(n.parent == f for n in tree.nodes)))]
        if not empty:
            return
        for f in empty:
            for n in tree.nodes:
                if n.parent == f:
                    n.parent = None
            tree.nodes.remove(f)


def _drop_unlinked_inputs(tree, only=None):
    """Group Input nodes with no links do nothing: remove them, keeping one if the tree would have none."""
    gis = [n for n in tree.nodes if n.bl_idname == 'NodeGroupInput']
    dead = [n for n in gis if (only is None or n.name in only) and not any(o.is_linked for o in n.outputs)]
    if len(dead) == len(gis):
        dead = dead[1:]
    for n in dead:
        tree.nodes.remove(n)


def _depth(specs):
    """Nesting depth of frame specs [(label, names, nested specs)]."""
    return 1 + max(_depth(kids) for _, _, kids in specs) if specs else 0


def _make_frames(tree, specs, parent, size, parent_of):
    """Create the frames of `specs` inside `parent`; parent_of[name] = the innermost frame of each node."""
    for lab, names, kids in specs:
        f = tree.nodes.new("NodeFrame")
        f.label = lab
        f.label_size = size
        f.parent = parent
        for k in names:
            parent_of[k] = f
        _make_frames(tree, kids, f, 12, parent_of)


def _arrange(tree, clusters, preds, succs, pos, only, frames, gap_x, gap_y, sink):
    """Lay clusters [(label, [names in topological order])] out at the origin: each cluster a block (_layout_region),
    blocks in dependency columns, the main chain (ending at the cluster of `sink`) on the top row, links that skip
    columns on lanes above. Returns (locations, width, height, frame specs [(label, names, nested specs)],
    main chain length, lane count). Frames are not created here, so a cluster can arrange its own steps."""
    cid = {k: i for i, (_, ms) in enumerate(clusters) for k in ms}
    blocks = [_layout_region(tree, ms, preds, succs, only, frames) for _, ms in clusters]
    for i, bl in enumerate(blocks):                         # reroutes created inside a cluster belong to it
        for k in bl[0]:
            cid.setdefault(k, i)
    # cluster graph
    cp = {i: set() for i in range(len(clusters))}
    for k in cid:
        for p in preds.get(k, ()):
            if p in cid and cid[p] != cid[k]:
                cp[cid[k]].add(cid[p])
    # cluster columns in dependency order (Kahn), so every link goes left -> right; a cycle (possible only with
    # hand-made frames) is broken at the cluster whose first node comes earliest
    first = {}                                      # first node that is not a Group Input (those are split per cluster)
    for i, (_, ms) in enumerate(clusters):
        first[i] = min((pos[k] for k in ms if tree.nodes[k].bl_idname != 'NodeGroupInput'),
                       default=min(pos[k] for k in ms))
    left = {i: set(cp[i]) for i in range(len(clusters))}
    ccol, done = {}, set()
    while len(done) < len(clusters):
        ready = [i for i in left if i not in done and not (left[i] - done)]
        if not ready:
            ready = [min((i for i in left if i not in done), key=lambda i: first[i])]
        for i in sorted(ready, key=lambda i: first[i]):
            ccol[i] = 1 + max((ccol[p] for p in cp[i] if p in ccol), default=-1)
            done.add(i)
    # pull each cluster right, to the column before its first consumer: clusters with no inputs of their own
    # (Collection Info, Object Info...) would otherwise sit in column 0 and send links across the whole tree.
    # Inside a cluster, the steps on the chain that enters it stay at the entry.
    fixed = _entry_chain(tree, sorted((k for _, ms in clusters for k in ms), key=lambda k: pos[k]), set(cid), preds)
    cs = {i: set() for i in range(len(clusters))}
    for i, ps in cp.items():
        for p in ps:
            cs[p].add(i)
    for i in sorted(ccol, key=lambda i: -ccol[i]):
        if any(k in fixed for k in clusters[i][1]):
            continue
        nxt = [ccol[s] for s in cs[i] if ccol[s] > ccol[i]]
        if nxt:
            ccol[i] = min(nxt) - 1
    # main chain: clusters on the path ending at the sink
    main = set()
    if sink in cid:
        cur = cid[sink]
        while cur not in main:                      # clusters need not be convex: guard against cycles
            main.add(cur)
            flow_p = [p for p in cp[cur] if p not in main and any(_is_flow(tree.nodes[k]) for k in clusters[p][1])]
            if not flow_p:
                break
            cur = max(flow_p, key=lambda p: ccol[p])
    ncol = max(ccol.values(), default=0) + 1
    colw = [0.0] * ncol
    for i, bl in enumerate(blocks):
        colw[ccol[i]] = max(colw[ccol[i]], bl[1])
    colx, x = [], 0.0
    for c in range(ncol):
        colx.append(x)
        x += colw[c] + gap_x
    by_col = {}
    for i in range(len(clusters)):
        by_col.setdefault(ccol[i], []).append(i)
    loc, specs, H = {}, [], 0.0
    for c, ids in by_col.items():
        ids.sort(key=lambda i: (i not in main, first[i]))
        y = 0.0
        for i in ids:
            bl, w, h, nested = blocks[i]
            ox, oy = colx[c] + (colw[c] - w) * 0.5 * (i not in main), y
            for k, (lx, ly) in bl.items():
                loc[k] = (ox + lx, oy + ly)
            if len(clusters[i][1]) > 1:
                specs.append((clusters[i][0], list(bl), nested))
            H = max(H, h - oy)
            y -= h + gap_y
    # links that skip cluster columns run on lanes above the clusters, through reroutes in the gaps. One lane per
    # source socket (its far targets branch off it). Shortest jumps first, each lane takes the lowest height above the
    # frames it crosses that no lane already uses over its stretch (it can slot under a higher lane once the lanes
    # in between have ended), so short links hug the frames and only long ones run high.
    gapx = [colx[c] - gap_x * 0.5 for c in range(ncol)]
    by_src = {}
    for l in list(tree.links):
        a, b_ = l.from_node.name, l.to_node.name
        if a not in cid or b_ not in cid or tree.nodes[a].bl_idname == 'NodeGroupInput':
            continue
        if ccol[cid[b_]] - ccol[cid[a]] > 1:
            by_src.setdefault((a, l.from_socket.identifier), []).append(l)
    jobs = []
    for (a, sid), ls in by_src.items():
        lo, hi = ccol[cid[a]] + 1, max(ccol[cid[l.to_node.name]] for l in ls)
        jobs.append((hi - lo, lo, a, sid, ls))
    ctop = [0.0] * ncol                                    # top of each column: its first cluster's frame
    for c, ids in by_col.items():
        if frames and len(clusters[ids[0]][1]) > 1:
            ctop[c] = FRAME_TOP + SUB_FRAME_TOP * _depth(blocks[ids[0]][3])
    used = {}                                              # gap -> heights of the lanes through it
    ys = set()
    for _, lo, a, sid, ls in sorted(jobs, key=lambda j: (j[0], j[1], j[2], j[3])):
        hi = max(ccol[cid[l.to_node.name]] for l in ls)
        ly = max(ctop[c] + LANE_GAP for c in range(lo, hi))
        while True:
            hit = [y_ for g in range(lo, hi + 1) for y_ in used.get(g, ()) if abs(y_ - ly) < LANE_GAP - 0.1]
            if not hit:
                break
            ly = max(hit) + LANE_GAP
        for g in range(lo, hi + 1):
            used.setdefault(g, []).append(ly)
        ys.add(round(ly))
        prev = next(o for o in tree.nodes[a].outputs if o.identifier == sid)
        chain = {}
        for c in range(lo, hi + 1):
            r = tree.nodes.new("NodeReroute")
            if only is not None:
                only.add(r.name)
            loc[r.name] = (gapx[c], ly)
            tree.links.new(prev, r.inputs[0])
            prev = chain[c] = r.outputs[0]
        for l in ls:
            _relink(tree, l, chain[ccol[cid[l.to_node.name]]])
    return loc, max(x - gap_x, 0.0), H, specs, len(main), len(ys)


def layout_clusters(tree, clusters=None, frames=True, split_inputs=True, keep_frames=True, only=None):
    """Lay out `tree` in labelled clusters. clusters: [(label, [node names])] or None for auto_clusters().
    Existing reroutes are dissolved first (the layout adds its own), so running it again gives the same result
    instead of turning old reroutes into clusters of their own. keep_frames=False ignores the existing frames
    (they are removed and the clusters are found from the graph).
    only: node names to lay out (the rest of the tree is left alone); the result keeps their top-left corner."""
    _measure_scale(tree)
    anchor = None
    if only is not None:
        only = {k for k in only if k in tree.nodes and tree.nodes[k].bl_idname != 'NodeFrame'}
        if not only:
            return {"clusters": 0, "main": 0, "lanes": 0}
        anchor = _corner(tree, only)
    _dissolve_reroutes(tree, only)
    _drop_unlinked_inputs(tree, only)
    if only is not None:
        only = {k for k in only if k in tree.nodes}
    if not keep_frames:
        _drop_frames(tree, only)
    nodes, preds, succs, order = _graph(tree, only)
    if clusters is None:
        clusters = auto_clusters(tree, only)
    pos = {k: i for i, k in enumerate(order)}
    clusters = [(lab, sorted(ms, key=lambda k: pos[k])) for lab, ms in clusters if ms]
    cid = {k: i for i, (_, ms) in enumerate(clusters) for k in ms}
    if split_inputs:
        # one Group Input per cluster, showing only the sockets that cluster uses (no long fan-out wires)
        for gi in [n for n in nodes if n.bl_idname == 'NodeGroupInput']:
            by_cl = {}
            for l in list(tree.links):
                if l.from_node == gi and l.to_node.name in cid:
                    by_cl.setdefault(cid[l.to_node.name], []).append(l)
            if len(by_cl) <= 1:
                continue
            home = cid.get(gi.name)
            for ci, ls in by_cl.items():
                if ci == home:
                    continue
                ng = tree.nodes.new("NodeGroupInput")
                used = set()
                for l in ls:
                    fid = l.from_socket.identifier
                    _relink(tree, l, next(o for o in ng.outputs if o.identifier == fid))
                    used.add(fid)
                for o in ng.outputs:
                    o.hide = bool(o.identifier) and o.identifier not in used
                clusters[ci][1].insert(0, ng.name)
                cid[ng.name] = ci
                if only is not None:
                    only.add(ng.name)
            for o in gi.outputs:
                o.hide = bool(o.identifier) and not o.is_linked
        nodes, preds, succs, order = _graph(tree, only)
        pos = {k: i for i, k in enumerate(order)}
        clusters = [(lab, sorted(ms, key=lambda k: pos[k])) for lab, ms in clusters]
    for n in nodes:                                            # unassigned nodes get their own cluster
        if n.name not in cid:
            cid[n.name] = len(clusters)
            clusters.append((n.label or n.bl_label, [n.name]))
    if frames:                                                 # old frames are replaced
        _drop_frames(tree, only)
    outs = [n.name for n in nodes if n.bl_idname in ('NodeGroupOutput', 'ShaderNodeOutputMaterial')]
    loc, _, _, specs, main, lane = _arrange(tree, clusters, preds, succs, pos, only, frames,
                                            CL_GAP_X, CL_GAP_Y + 40, outs[0] if outs else None)
    parent_of = {}
    if frames:
        _make_frames(tree, specs, None, 16, parent_of)
    for k, (x, y) in loc.items():
        n = tree.nodes[k]
        if k in parent_of:
            n.parent = parent_of[k]
        _set_loc(n, x, y)
    if only is not None:                                   # reroutes made inside clusters are laid-out nodes too
        only.update(loc)
    _thin_reroutes(tree, only)
    if anchor is not None:                                 # back where the selection was
        only = {k for k in only if k in tree.nodes}
        x0, y0 = _corner(tree, only)
        for k in only:
            n = tree.nodes[k]
            if n.bl_idname != 'NodeFrame':
                x, y = _abs_loc(n)
                _set_loc(n, x + anchor[0] - x0, y + anchor[1] - y0)
    return {"clusters": len(clusters), "main": main, "lanes": lane}


def layout_detached(tree, **kw):
    """layout_clusters() on a group while nothing uses it. Editing a group that other trees use makes Blender
    update every user tree after each edit (minutes for big shared groups); so its users are pointed at a
    placeholder copy for the duration, then pointed back. Material / world trees are laid out directly."""
    if tree.is_embedded_data or tree.users - (1 if tree.use_fake_user else 0) <= 0:
        return layout_clusters(tree, **kw)
    ph = tree.copy()
    tree.user_remap(ph)
    try:
        return layout_clusters(tree, **kw)
    finally:
        ph.user_remap(tree)
        bpy.data.node_groups.remove(ph)


def nested_groups(tree):
    """Local node groups used inside `tree`, at any depth (linked ones can't be edited), innermost first."""
    out, seen = [], {tree.name}

    def visit(t):
        for n in t.nodes:
            ng = getattr(n, "node_tree", None)
            if ng is None or ng.name in seen or ng.library is not None or ng.bl_idname != tree.bl_idname:
                continue
            seen.add(ng.name)
            visit(ng)
            out.append(ng)
    visit(tree)
    return out


def _selected(tree):
    """Selected nodes, plus everything inside a selected frame."""
    sel = {n.name for n in tree.nodes if n.select and n.bl_idname != 'NodeFrame'}
    frames = {n for n in tree.nodes if n.select and n.bl_idname == 'NodeFrame'}
    for n in tree.nodes:
        f = n.parent
        while f is not None:
            if f in frames and n.bl_idname != 'NodeFrame':
                sel.add(n.name)
                break
            f = f.parent
    return sel


class NODE_OT_qp_cluster_layout(Operator):
    """Lay the node tree out in framed clusters, every link going left to right"""
    bl_idname = "node.qp_cluster_layout"
    bl_label = "Cluster Layout"
    bl_options = {'REGISTER', 'UNDO'}

    scope: EnumProperty(
        name="Scope",
        items=[
            ('SELECTED', "Selected Nodes", "Lay out the selected nodes (and the nodes in selected frames) where they "
                                           "are, leaving the rest of the tree alone"),
            ('ALL', "All Nodes", "Lay out every node of the current tree"),
            ('FULL', "Full Tree", "Lay out the current tree and every node group nested inside it"),
        ],
        default='ALL',
    )
    keep_frames: BoolProperty(
        name="Keep Frames",
        description="Use the existing frames as clusters. Off: the frames are removed and the clusters are found "
                    "from the node graph (frames where links leave and come back can't be laid out left to right)",
        default=True,
    )
    frames: BoolProperty(
        name="Frames",
        description="Put each cluster in a labelled frame",
        default=True,
    )
    split_inputs: BoolProperty(
        name="Split Group Inputs",
        description="One Group Input per cluster, showing only the sockets it uses",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return (module_enabled and context.space_data is not None
                and context.space_data.type == 'NODE_EDITOR' and context.space_data.edit_tree is not None)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "scope", expand=True)
        col.separator()
        col.prop(self, "keep_frames")
        col.prop(self, "frames")
        col.prop(self, "split_inputs")

    def execute(self, context):
        tree = context.space_data.edit_tree
        kw = dict(frames=self.frames, split_inputs=self.split_inputs, keep_frames=self.keep_frames)
        t0 = time.perf_counter()
        if self.scope == 'SELECTED':
            sel = _selected(tree)
            if not sel:
                self.report({'WARNING'}, "No nodes selected")
                return {'CANCELLED'}
            res = layout_detached(tree, only=sel, **kw)
            msg = f"{res['clusters']} clusters"
        elif self.scope == 'FULL':
            groups = nested_groups(tree)
            n = sum(layout_detached(ng, **kw)["clusters"] for ng in groups)
            res = layout_detached(tree, **kw)
            msg = f"{res['clusters'] + n} clusters in {len(groups) + 1} trees"
        else:
            res = layout_detached(tree, **kw)
            msg = f"{res['clusters']} clusters"
        self.report({'INFO'}, f"{msg} laid out in {time.perf_counter() - t0:.1f} s")
        return {'FINISHED'}


def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return

    ModuleManager.safe_register_class(NODE_OT_qp_cluster_layout)


def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return

    ModuleManager.safe_unregister_class(NODE_OT_qp_cluster_layout)
