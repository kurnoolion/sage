#!/usr/bin/env python3
"""Dedicated view of the DOMAIN HIERARCHY (concept scheme) as a top-down tree.

Renders concept-scheme/domain-concept-scheme.json with a hierarchical layout
(UE -> strata -> layers via BROADER), each concept annotated with how many KG
entities are classified under it (IN_LAYER), in-scope vs out-of-scope shown.
Self-contained; open via file://.

Output (gitignored): rrc-pilot/viz/concept-view.html
"""
import json, os

ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT = os.path.join(ROOT, "rrc-pilot")
def load(p, d=None):
    try:
        with open(p) as f: return json.load(f)
    except FileNotFoundError: return d

SCHEME = load(os.path.join(PILOT, "concept-scheme/domain-concept-scheme.json"))
KG     = load(os.path.join(PILOT, "knowledge-graph/kg.json"))
SPEC   = "%s %s" % (KG["spec"], KG["version"])
CONC   = SCHEME["concepts"]

TYPE_COLOR = {"DomainRoot":"#2c3e50", "Stratum":"#566573", "ProtocolLayer":"#95a5a6"}

# depth from root via broader (for hierarchical levels)
def depth(cid):
    d, cur = 0, cid
    while CONC.get(cur, {}).get("broader"):
        cur = CONC[cur]["broader"]; d += 1
    return d

# IN_LAYER counts + sample member labels, from the KG
label_by = {e["id"]: e["label"] for e in KG["entities"]}
members = {cid: [] for cid in CONC}
for r in KG["relations"]:
    if r["type"] == "IN_LAYER" and r["to"] in members:
        members[r["to"]].append(label_by.get(r["from"], r["from"]))

nodes, edges = [], []
for cid, c in CONC.items():
    n = len(members[cid]); insc = c.get("in_scope", True)
    bg = TYPE_COLOR.get(c["type"], "#999")
    nodes.append({
        "id": cid, "label": "%s\n(%d)" % (c["label"], n) if n else c["label"],
        "level": depth(cid), "shape": "box",
        "color": {"background": bg if insc else "#d5d8dc",
                  "border": "#1f2d3d" if insc else "#aab"},
        "borderWidth": 2, "borderWidthSelected": 3,
        "font": {"color": "#fff" if insc else "#666", "size": 14, "multi": True},
        "shapeProperties": {"borderDashes": (not insc)},
        "size": 16 + min(n, 30),
        "meta": {"id": cid, "label": c["label"], "type": c["type"],
                 "broader": c.get("broader"), "in_scope": insc,
                 "count": n, "members": members[cid]},
    })
for cid, c in CONC.items():
    if c.get("broader"):
        edges.append({"from": c["broader"], "to": cid, "arrows": "to",
                      "color": {"color": "#9aa0a6"}, "label": "BROADER", "font": {"size": 8, "color": "#99a"}})

DATA = json.dumps({"nodes": nodes, "edges": edges})

HTML = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Domain hierarchy — {SPEC}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
 *{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;color:#222}}
 header{{padding:10px 16px;background:#1f2d3d;color:#fff}}
 header h1{{margin:0;font-size:17px}} header p{{margin:4px 0 0;font-size:12px;color:#cfd8e3}}
 #wrap{{display:flex;height:calc(100vh - 60px)}}
 #net{{flex:1;background:#fafbfc}}
 #panel{{width:340px;border-left:1px solid #d9dee3;padding:14px 16px;overflow:auto;background:#fff}}
 #panel h2{{font-size:14px;margin:0 0 8px}}
 .badge{{display:inline-block;font-size:11px;padding:2px 7px;border-radius:10px;color:#fff;margin-right:5px}}
 .kv{{font-size:12px;margin:5px 0 2px;color:#444}} .kv b{{color:#111}}
 #panel ul{{margin:4px 0;padding-left:18px;font-size:12px}} #panel li{{margin:2px 0}}
 .hint{{color:#888;font-size:12px}}
</style></head><body>
<header><h1>Domain hierarchy (concept scheme) — {SPEC}</h1>
 <p>Curated protocol-stack tree via <code>BROADER</code>. Number in each box = KG entities classified under it (<code>IN_LAYER</code>). Faded/dashed = out of v1 scope. Click a concept for details.</p></header>
<div id="wrap"><div id="net"></div><div id="panel"><p class="hint">Click a concept.</p></div></div>
<script>
const DATA={DATA};
const nodes=new vis.DataSet(DATA.nodes), edges=new vis.DataSet(DATA.edges);
const net=new vis.Network(document.getElementById('net'),{{nodes,edges}},{{
  layout:{{hierarchical:{{enabled:true,direction:'UD',sortMethod:'directed',levelSeparation:120,nodeSpacing:150}}}},
  physics:false, interaction:{{hover:true,dragNodes:true}}}});
const panel=document.getElementById('panel');
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function chain(id){{const out=[];let c=id;while(c){{out.push(nodes.get(c).meta.label);c=nodes.get(c).meta.broader;}}return out;}}
net.on('selectNode',p=>{{
  const m=nodes.get(p.nodes[0]).meta;
  const kids=DATA.nodes.filter(n=>n.meta.broader===m.id).map(n=>n.meta.label);
  const mem=m.members.slice(0,25);
  panel.innerHTML=`<h2>${{esc(m.label)}}</h2>
   <span class="badge" style="background:${{m.in_scope?'#27ae60':'#aab'}}">${{m.in_scope?'in v1 scope':'out of v1 scope'}}</span>
   <div class="kv"><b>id:</b> ${{esc(m.id)}}</div>
   <div class="kv"><b>ontology type:</b> ${{esc(m.type)}}</div>
   <div class="kv"><b>broader chain:</b> ${{esc(chain(m.id).join(' → '))}}</div>
   <div class="kv"><b>narrower:</b> ${{kids.length?esc(kids.join(', ')):'(none)'}}</div>
   <div class="kv"><b>KG entities IN_LAYER (${{m.count}}):</b></div>
   ${{mem.length?('<ul>'+mem.map(x=>`<li>${{esc(x)}}</li>`).join('')+(m.count>25?`<li>… +${{m.count-25}} more</li>`:'')+'</ul>'):'<p class="hint">none yet</p>'}}`;
}});
</script></body></html>"""

out = os.path.join(os.path.dirname(__file__), "concept-view.html")
open(out, "w").write(HTML)
print("wrote", out, "(%d concepts)" % len(nodes))
