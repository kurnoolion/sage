#!/usr/bin/env python3
"""Generic, data-driven KG viewer.

Renders ANY kg.json (+ ontology + corpus + concept scheme) into a self-contained
HTML you open via file:// — no server. Nothing here is RRC-specific:
  - node colours come from the ontology's entity types,
  - focus buttons are derived from the data's `procedure_ctx` values,
  - clause (corpus) nodes are the provenance-referenced clauses + ancestors.

Incremental: on each open it highlights nodes/edges that are NEW since you last
viewed this KG (browser localStorage), with a "Mark all as seen" reset.

Output (gitignored — embeds spec prose): rrc-pilot/viz/kg-view.html
"""
import argparse, json, os

ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PILOT = os.path.join(ROOT, "rrc-pilot")

def load(p, default=None):
    try:
        with open(p) as f: return json.load(f)
    except FileNotFoundError:
        return default

# Generic: render ANY kg.json / extraction snapshot. Defaults = the RRC pilot;
# point --kg/--ontology elsewhere (e.g. a pipeline snapshot) to view that graph.
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--kg", default=os.path.join(PILOT, "knowledge-graph/kg.json"),
                help="KG / snapshot JSON (entities + relations).")
ap.add_argument("--ontology", default=os.path.join(PILOT, "ontology/ontology.json"),
                help="ontology JSON (entity_types drive node colours + legend).")
ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "kg-view.html"),
                help="output HTML path.")
ap.add_argument("--title", default=None, help="title override (default '<spec> <version>').")
ARGS = ap.parse_args()

KG   = load(ARGS.kg)
ONTO = load(ARGS.ontology, {})
SPEC = ARGS.title or ("%s %s" % (KG["spec"], KG["version"]))
speckey = KG["spec"].replace("TS ", "").replace(".", "")
CORP = load(os.path.join(ROOT, "corpus/store/%s-%s/clauses.json" % (speckey, KG["version"])),
            {"clauses": {}})
CLAUSES = CORP.get("clauses", {})

# --- colours: known types styled nicely; unknown types get a fallback palette ---
BASE = {"Procedure":"#e74c3c","Message":"#3498db","InformationElement":"#1abc9c",
        "Timer":"#f39c12","State":"#9b59b6","Bearer":"#27ae60","Event":"#e67e22",
        "UEVariable":"#34495e","ProtocolLayer":"#95a5a6","Condition":"#c0392b",
        "Stratum":"#566573","DomainRoot":"#2c3e50"}
FALLBACK = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2",
            "#7f7f7f","#bcbd22","#17becf"]
SIZE = {"DomainRoot":30,"Stratum":24,"ProtocolLayer":22,"Procedure":26,"Message":20}
etypes = list(ONTO.get("entity_types", {}).keys()) or sorted({e["type"] for e in KG["entities"]})
COLORS = {t: (BASE.get(t) or FALLBACK[i % len(FALLBACK)]) for i, t in enumerate(etypes)}
CLAUSE_BG, CLAUSE_BORDER = "#fff7e6", "#b8860b"

CURREL = KG.get("current_release")

def pick(plist):
    """Choose the provenance record to display: the current-release clause record if
    present, else any clause record, else the first (external/curated)."""
    plist = plist or [{"curated": True}]
    crecs = [p for p in plist if p.get("clause")]
    if crecs:
        for p in crecs:
            if p.get("release") == CURREL: return p
        return crecs[0]
    return plist[0]

def prov_text(plist):
    p = pick(plist)
    if p.get("curated"):  return "Curated (concept scheme / release) — not from a clause."
    if p.get("external"): return "Defined in external spec: %s" % p.get("spec")
    c = CLAUSES.get(p.get("clause") or "")
    if not c: return "(clause %s — corpus not loaded)" % p.get("clause")
    num = c.get("number");  num = num if (num and num[:1].isdigit()) else c["key"]
    extra = "" if len([x for x in plist if x.get("clause")]) < 2 else \
            " [also: %s]" % ", ".join("%s§%s" % (x.get("release"), x.get("clause")) for x in plist if x.get("clause") and x is not p)
    return "Clause %s — %s%s\n\n%s" % (num, c["title"], extra, (c["text"] or "(container clause)")[:700])

# --- nodes: entities + concepts ---
nodes = []
for e in KG["entities"]:
    t, isC = e["type"], e.get("concept", False)
    bg = COLORS.get(t, "#999"); p = pick(e["defined_in"])
    where = p.get("clause") or p.get("spec") or ("concept:" + (e.get("in_scheme") or ""))
    nodes.append({"id": e["id"], "label": e["label"], "group": t,
        "color": {"background": bg, "border": "#2c3e50"}, "borderWidth": 1,
        "size": SIZE.get(t, 15), "shape": "diamond" if isC else "dot", "font": {"size": 13},
        "title": "%s%s — %s" % (t, " · concept" if isC else "", where),
        "meta": {"kind": "concept" if isC else "entity", "type": t, "bg": bg,
                 "where": where, "prov": prov_text(e["defined_in"]),
                 "observed_in": e.get("observed_in", []), "introduced_in": e.get("introduced_in"),
                 "valid_until": e.get("valid_until"),
                 "in_scheme": e.get("in_scheme"), "in_scope": e.get("in_scope")}})

# --- edges: KG relations ---
MODCOLOR = {"asn1":"#2c7fb8","prose":"#b0a8a0","curated":"#c9a0dc",
            "deterministic":"#d9c089","provenance":"#9aa0a6"}
edges = []
for r in KG["relations"]:
    mod = r["modality"]; base = MODCOLOR.get(mod, "#b0a8a0"); pp = pick(r["provenance"])
    attrs = ", ".join("%s: %s" % (k, v) for k, v in (r.get("attrs") or {}).items())
    edges.append({"id": r["id"], "from": r["from"], "to": r["to"], "label": r["type"],
        "arrows": "to", "dashes": (mod != "asn1"), "width": 1, "color": {"color": base},
        "font": {"size": 9, "align": "middle", "color": "#555"},
        "meta": {"kind": "rel", "rel": r["type"], "modality": mod, "basecolor": base,
                 "confidence": r["confidence"], "clause": pp.get("clause"),
                 "anchor": pp.get("anchor"), "attrs": attrs, "proc": r.get("procedure_ctx", ""),
                 "observed_in": r.get("observed_in", []), "introduced_in": r.get("introduced_in"),
                 "valid_until": r.get("valid_until")}})

# --- corpus clause nodes: provenance-referenced clauses + ancestors ---
def cid(k): return "C_" + k.replace(".", "_").replace("/", "__")
ref = set()
for r in KG["relations"]:
    c = pick(r["provenance"]).get("clause")
    if c in CLAUSES: ref.add(c)
for e in KG["entities"]:
    c = pick(e["defined_in"]).get("clause")
    if c in CLAUSES: ref.add(c)
spine = set()
for c in ref:
    cur = c
    while cur in CLAUSES and cur not in spine:
        spine.add(cur); cur = CLAUSES[cur].get("parent") or ""
for k in sorted(spine):
    c = CLAUSES[k]
    nodes.append({"id": cid(k), "label": (c.get("number") or k), "group": "Clause",
        "color": {"background": CLAUSE_BG, "border": CLAUSE_BORDER}, "borderWidth": 1,
        "shape": "box", "font": {"size": 12, "color": "#6b4e16"},
        "title": "Clause %s — click for full prose" % k,
        "meta": {"kind": "clause", "bg": CLAUSE_BG, "clause": k, "title": c["title"],
                 "text": c["text"] or "(container clause — no direct prose)"}})
for k in spine:                                            # clause tree
    p = CLAUSES[k].get("parent")
    if p in spine:
        edges.append({"id": "ct_" + cid(k), "from": cid(p), "to": cid(k), "label": "CONTAINS",
            "arrows": "to", "dashes": False, "width": 1, "color": {"color": MODCOLOR["deterministic"]},
            "font": {"size": 8, "color": "#a98"},
            "meta": {"kind": "rel", "rel": "CONTAINS", "modality": "deterministic",
                     "basecolor": MODCOLOR["deterministic"], "confidence": "high",
                     "clause": k, "anchor": "", "attrs": "document tree", "proc": "_spine"}})
for e in KG["entities"]:                                   # DEFINED_IN into the spine
    c = pick(e["defined_in"]).get("clause")
    if c in spine:
        edges.append({"id": "di_" + e["id"], "from": e["id"], "to": cid(c), "label": "DEFINED_IN",
            "arrows": "to", "dashes": True, "width": 1, "color": {"color": MODCOLOR["provenance"]},
            "font": {"size": 8, "color": "#99a"},
            "meta": {"kind": "rel", "rel": "DEFINED_IN", "modality": "provenance",
                     "basecolor": MODCOLOR["provenance"], "confidence": "high",
                     "clause": c, "anchor": "", "attrs": "provenance", "proc": "_spine"}})

# focus values from data (procedure contexts), excluding shared/spine/concept/empty
PROCS = sorted({r.get("procedure_ctx", "") for r in KG["relations"]}
               - {"", "shared", "concept", "_spine"})
DATA = json.dumps({"nodes": nodes, "edges": edges})
LEGEND = "".join(f'<span class="lg"><i style="background:{COLORS.get(t,"#999")}"></i>{t}</span>'
                 for t in etypes)
FOCUS_BTNS = '<button data-f="all" class="active">All</button>' + "".join(
    f'<button data-f="{p}">{p}</button>' for p in PROCS)

HTML = f"""<!doctype html><html><head><meta charset="utf-8">
<title>KG view — {SPEC}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
 *{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;color:#222}}
 header{{padding:10px 16px;background:#1f2d3d;color:#fff}}
 header h1{{margin:0;font-size:17px}} header p{{margin:4px 0 0;font-size:12px;color:#cfd8e3}}
 #bar{{padding:6px 16px;background:#eef1f4;border-bottom:1px solid #d9dee3;font-size:12px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}}
 #bar button{{font-size:12px;padding:3px 10px;border:1px solid #aab;border-radius:4px;background:#fff;cursor:pointer}}
 #bar button.active{{background:#1f2d3d;color:#fff;border-color:#1f2d3d}}
 #bar .sep{{width:1px;height:18px;background:#ccd;margin:0 6px}}
 .lg{{display:inline-flex;align-items:center;gap:4px;margin-right:4px}}
 .lg i{{width:11px;height:11px;border-radius:50%;display:inline-block}}
 #wrap{{display:flex;height:calc(100vh - 96px)}}
 #net{{flex:1;background:#fafbfc}}
 #panel{{width:390px;border-left:1px solid #d9dee3;padding:14px 16px;overflow:auto;background:#fff}}
 #panel h2{{font-size:14px;margin:0 0 8px}}
 .badge{{display:inline-block;font-size:11px;padding:2px 7px;border-radius:10px;color:#fff;margin-right:5px}}
 .kv{{font-size:12px;margin:5px 0 2px;color:#444}} .kv b{{color:#111}}
 pre.spec{{white-space:pre-wrap;background:#f6f8fa;border:1px solid #e1e4e8;border-left:3px solid #1f6feb;
   padding:9px 11px;border-radius:4px;font-size:12px;line-height:1.45;margin-top:8px;color:#24292e}}
 .hint{{color:#888;font-size:12px}} .modline{{font-size:11px;color:#666;margin-top:6px}}
 code{{background:#eef;padding:0 3px;border-radius:3px}}
 mark.hl{{background:#fff3b0;border-radius:2px;padding:0 1px;cursor:pointer}}
 mark.hl.active{{background:#ffd23f;outline:1px solid #e6a700}}
 #panel ul{{margin:4px 0;padding-left:18px}}
 #panel li{{font-size:12px;margin:3px 0;cursor:pointer;border-radius:3px;padding:1px 3px}}
 #panel li.active{{background:#fff3b0}}
 .cov{{font-size:11px;color:#2e7d32;margin:6px 0;font-weight:600}}
</style></head><body>
<header>
 <h1>Knowledge graph — {SPEC}</h1>
 <p>Generic view of <code>kg.json</code> (+ corpus). Round = entities, diamond = concepts, gold box = corpus clauses. <b>New items since you last opened are ringed green.</b> Solid edges = ASN.1; dashed = prose / provenance.</p>
</header>
<div id="bar">
 <b>Focus:</b> {FOCUS_BTNS}
 <span class="sep"></span>
 <button id="spineBtn">Corpus clauses: OFF</button>
 <button id="conceptBtn">Concept scheme: OFF</button>
 <span class="sep"></span>
 <button id="newBtn" class="active">Highlight new: ON</button>
 <button id="seenBtn">Mark all as seen</button>
 <span style="margin-left:8px">{LEGEND}</span>
</div>
<div id="wrap"><div id="net"></div><div id="panel"></div></div>
<script>
const SPEC="{SPEC}";
const DATA={DATA};
const nodes=new vis.DataSet(DATA.nodes), edges=new vis.DataSet(DATA.edges);
const net=new vis.Network(document.getElementById('net'),{{nodes,edges}},{{
  physics:{{stabilization:true,barnesHut:{{gravitationalConstant:-9000,springLength:150,springConstant:0.03}}}},
  interaction:{{hover:true,tooltipDelay:200}}, edges:{{smooth:{{type:'dynamic'}}}}}});
const panel=document.getElementById('panel');
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// ---- "new since last view" via localStorage ----
const ALL=DATA.nodes.map(n=>n.id).concat(DATA.edges.map(e=>e.id));
const KEY='kgseen::'+SPEC;
let NEW=new Set(), firstView=false;
(function(){{ let st=null; try{{st=JSON.parse(localStorage.getItem(KEY));}}catch(e){{}}
  if(st&&Array.isArray(st)){{ const s=new Set(st); NEW=new Set(ALL.filter(id=>!s.has(id))); }}
  else {{ firstView=true; localStorage.setItem(KEY,JSON.stringify(ALL)); }} }})();
let highlightNew=true;
function applyHighlight(){{
  nodes.forEach(n=>{{ const hot=highlightNew&&NEW.has(n.id);
    nodes.update({{id:n.id,borderWidth:hot?4:1,
      color:{{background:n.meta.bg,border:hot?'#2ecc71':(n.meta.kind==='clause'?'#b8860b':'#2c3e50')}}}}); }});
  edges.forEach(e=>{{ const hot=highlightNew&&NEW.has(e.id);
    edges.update({{id:e.id,width:hot?3:1,color:{{color:hot?'#2ecc71':e.meta.basecolor}}}}); }});
}}

// ---- stats (default panel) ----
function showStats(){{
  const nt={{}},rt={{}}; let nnew=0,enew=0;
  DATA.nodes.forEach(n=>{{const k=n.meta.kind==='clause'?'Clause':n.meta.type; nt[k]=(nt[k]||0)+1; if(NEW.has(n.id))nnew++;}});
  DATA.edges.forEach(e=>{{rt[e.meta.rel]=(rt[e.meta.rel]||0)+1; if(NEW.has(e.id))enew++;}});
  const li=o=>'<ul>'+Object.entries(o).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<li>${{esc(k)}} — ${{v}}</li>`).join('')+'</ul>';
  panel.innerHTML=`<h2>${{SPEC}} — knowledge graph</h2>
   <div class="kv"><b>${{DATA.nodes.length}}</b> nodes · <b>${{DATA.edges.length}}</b> edges</div>
   <div class="cov">${{firstView?'First view — baseline set; nothing marked new yet.':(nnew+' new node(s) + '+enew+' new edge(s) since you last viewed.')}}</div>
   <div class="kv"><b>Entities by type:</b></div>${{li(nt)}}
   <div class="kv"><b>Relations by type:</b></div>${{li(rt)}}
   <p class="hint">Click a node / edge / clause to inspect. Toggle corpus clauses & concept scheme above.</p>`;
}}

function showNode(id){{
  const n=nodes.get(id),m=n.meta;
  const life=`observed ${{(m.observed_in||[]).join(', ')||'—'}} · introduced ${{m.introduced_in||'?'}} · valid until ${{m.valid_until||'current'}}`;
  panel.innerHTML=`<h2>${{esc(n.label)}}${{NEW.has(id)?' <span class="badge" style="background:#2ecc71">NEW</span>':''}}</h2>
   <span class="badge" style="background:${{m.bg}}">${{m.type}}${{m.kind==='concept'?' · concept':''}}</span>
   <div class="kv"><b>Defined in:</b> ${{esc(m.where)}}</div>
   <div class="kv"><b>Releases:</b> ${{esc(life)}}</div>
   <div class="modline">resolved from the corpus document store:</div>
   <pre class="spec">${{esc(m.prov)}}</pre>`;
}}
function showEdge(id){{
  const e=edges.get(id),m=e.meta,a=nodes.get(e.from).label,b=nodes.get(e.to).label;
  panel.innerHTML=`<h2>${{esc(a)}} &rarr; ${{esc(b)}}${{NEW.has(id)?' <span class="badge" style="background:#2ecc71">NEW</span>':''}}</h2>
   <span class="badge" style="background:#444">${{m.rel}}</span>
   <span class="badge" style="background:${{m.modality=='asn1'?'#2c7fb8':'#b0772f'}}">${{m.modality}}</span>
   <span class="badge" style="background:#777">conf: ${{m.confidence}}</span>
   <div class="kv"><b>Releases:</b> observed ${{(m.observed_in||[]).join(', ')||'—'}}${{m.valid_until?(' · valid until '+m.valid_until):' · current'}}</div>
   ${{m.clause?`<div class="kv"><b>Provenance:</b> clause ${{esc(m.clause)}}</div>`:''}}
   ${{m.attrs?`<div class="kv"><b>Attributes:</b> ${{esc(m.attrs)}}</div>`:''}}
   ${{m.anchor?`<div class="kv"><b>Anchor:</b></div><pre class="spec">${{esc(m.anchor)}}</pre>`:''}}`;
}}
function showClause(id){{
  const c=nodes.get(id),m=c.meta,prose=m.text;
  const facts=edges.get().filter(e=>e.meta.kind==='rel'&&e.meta.clause===m.clause&&e.meta.rel!=='CONTAINS'&&e.meta.rel!=='DEFINED_IN');
  const locate=raw=>{{ let a=(raw||'').replace(/^[ .;:,]+/,'').replace(/[ .;:,]+$/,''); if(!a)return null;
    let i=prose.indexOf(a); if(i>=0)return[i,a.length];
    const w=a.split(' '); for(let st=1;st<=w.length-3;st++){{const sub=w.slice(st).join(' ');const j=prose.indexOf(sub);if(j>=0)return[j,sub.length];}}
    const h=a.slice(0,40),k=prose.indexOf(h); if(k>=0)return[k,h.length]; return null; }};
  const ranges=[]; facts.forEach(e=>{{const r=locate(e.meta.anchor); if(r)ranges.push({{s:r[0],e:r[0]+r[1],id:e.id}});}});
  ranges.sort((x,y)=>x.s-y.s); let body='',cur=0;
  ranges.forEach(r=>{{ if(r.s<cur)return; body+=esc(prose.slice(cur,r.s))+`<mark class="hl" data-edge="${{r.id}}">`+esc(prose.slice(r.s,r.e))+`</mark>`; cur=r.e; }});
  body+=esc(prose.slice(cur));
  const fl=facts.length?('<ul>'+facts.map(e=>`<li data-edge="${{e.id}}"><code>${{esc(nodes.get(e.from).label)}}</code> <b>${{e.meta.rel}}</b> <code>${{esc(nodes.get(e.to).label)}}</code></li>`).join('')+'</ul>'):'<p class="hint">no facts extracted from this clause</p>';
  panel.innerHTML=`<h2>Clause ${{esc(m.clause)}} — ${{esc(m.title)}}</h2>
   <span class="badge" style="background:#b8860b">corpus clause</span>
   <div class="kv">full verbatim prose; <mark class="hl">highlighted</mark> spans became facts:</div>
   <pre class="spec">${{body}}</pre>
   <div class="kv"><b>Facts extracted here:</b></div>${{fl}}
   <div class="modline">Complete prose retained verbatim; highlighted = became a KG edge; the rest is kept but not structured.</div>`;
  const set=(eid,on)=>panel.querySelectorAll(`[data-edge="${{eid}}"]`).forEach(el=>el.classList.toggle('active',on));
  panel.querySelectorAll('li[data-edge]').forEach(li=>{{li.onmouseover=()=>set(li.dataset.edge,true);li.onmouseout=()=>set(li.dataset.edge,false);li.onclick=()=>net.selectEdges([li.dataset.edge]);}});
  panel.querySelectorAll('mark[data-edge]').forEach(mk=>{{mk.onmouseover=()=>set(mk.dataset.edge,true);mk.onmouseout=()=>set(mk.dataset.edge,false);mk.onclick=()=>net.selectEdges([mk.dataset.edge]);}});
}}
net.on('selectNode',p=>{{const m=nodes.get(p.nodes[0]).meta; (m.kind==='clause')?showClause(p.nodes[0]):showNode(p.nodes[0]);}});
net.on('selectEdge',p=>{{if(p.nodes.length===0)showEdge(p.edges[0]);}});
net.on('click',p=>{{if(p.nodes.length===0&&p.edges.length===0)showStats();}});

// ---- filters ----
let focus='all',spineOn=false,conceptOn=false;
const cls=e=>(e.meta.rel==='IN_LAYER'||e.meta.rel==='BROADER')?'concept':(e.meta.proc==='_spine'?'spine':'behavioral');
function applyFilter(){{
  const ev={{}}, nv={{}};
  edges.forEach(e=>{{ const k=cls(e); ev[e.id]=(k==='concept')?conceptOn:(k==='spine')?spineOn:((focus==='all')||(e.meta.proc===focus)||(e.meta.proc==='shared')); }});
  nodes.forEach(n=>{{ const k=n.meta.kind; let v;
    if(k==='concept')v=conceptOn; else if(k==='clause')v=spineOn;
    else if(focus==='all')v=true; else {{ v=false; edges.forEach(e=>{{ if(ev[e.id]&&cls(e)==='behavioral'&&(e.from===n.id||e.to===n.id))v=true; }}); }}
    nv[n.id]=v; }});
  nodes.forEach(n=>nodes.update({{id:n.id,hidden:!nv[n.id]}}));
  edges.forEach(e=>edges.update({{id:e.id,hidden:!(ev[e.id]&&nv[e.from]&&nv[e.to])}}));
}}
document.querySelectorAll('#bar button[data-f]').forEach(btn=>btn.onclick=()=>{{
  document.querySelectorAll('#bar button[data-f]').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active'); focus=btn.dataset.f; applyFilter(); }});
const tog=(id,lbl,get,set)=>{{const b=document.getElementById(id);b.onclick=()=>{{set(!get());b.textContent=lbl+': '+(get()?'ON':'OFF');b.classList.toggle('active',get());applyFilter();}};}};
tog('spineBtn','Corpus clauses',()=>spineOn,v=>spineOn=v);
tog('conceptBtn','Concept scheme',()=>conceptOn,v=>conceptOn=v);
document.getElementById('newBtn').onclick=function(){{highlightNew=!highlightNew;this.textContent='Highlight new: '+(highlightNew?'ON':'OFF');this.classList.toggle('active',highlightNew);applyHighlight();}};
document.getElementById('seenBtn').onclick=()=>{{localStorage.setItem(KEY,JSON.stringify(ALL));NEW=new Set();firstView=false;applyHighlight();showStats();}};
applyFilter(); applyHighlight(); showStats();
</script></body></html>"""

open(ARGS.out, "w").write(HTML)
print("wrote", ARGS.out, "(%d nodes, %d edges; %d focus contexts)" % (len(nodes), len(edges), len(PROCS)))

