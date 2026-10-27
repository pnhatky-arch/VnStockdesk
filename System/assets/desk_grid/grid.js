/* Local, dependency-free Streamlit v1 component. Never accesses parent DOM. */
"use strict";
let args, rows = [], revision, query = "", page = 0, sort = null;
const $ = s => document.querySelector(s), size = 50;
const parentOrigin = new URL(document.referrer || location.href).origin;
function send(type, fields = {}) { parent.postMessage({isStreamlitMessage:true,type,...fields}, parentOrigin); }
function height() { send("streamlit:setFrameHeight", {height:Math.ceil(document.body.scrollHeight)+2}); }
function publish() { send("streamlit:setComponentValue", {dataType:"json",value:{revision,rows}}); }
function node(tag, text) { const el = document.createElement(tag); if(text != null) el.textContent = text; return el; }
function format(value, col) {
  if(value == null) return "—";
  const fmt = col.format, number = Number(value);
  if(fmt && Number.isFinite(number) && fmt.startsWith("vn_")) {
    const signed=fmt.includes("signed"), money=fmt.includes("vnd"), digits=fmt.includes("decimal3")?3:0;
    const rendered=new Intl.NumberFormat("vi-VN",{
      minimumFractionDigits:digits,maximumFractionDigits:digits,signDisplay:signed?"always":"auto"
    }).format(number);
    return rendered+(money?" ₫":"");
  }
  if(fmt && Number.isFinite(number)) {
    return fmt.replace(/%([+]?)(?:\.(\d+))?([fd])/g, (_,sign,precision,type) =>
      (sign && number >= 0 ? "+" : "") + number.toFixed(type === "d" ? 0 : Number(precision ?? 6))).replace(/%%/g,"%");
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function filtered() {
  let list = rows.map((row,index)=>({row,index})).filter(({row})=>args.columns.some(col=>String(row[col.name]??"").toLocaleLowerCase().includes(query)));
  if(sort) list.sort((a,b)=>{
    const x=a.row[sort.name],y=b.row[sort.name];
    return sort.direction*(typeof x === "number" && typeof y === "number" ? x-y : String(x??"").localeCompare(String(y??""),undefined,{numeric:true}));
  });
  return list;
}
function draw() {
  const list=filtered(); page=Math.min(page,Math.max(0,Math.ceil(list.length/size)-1));
  const head=node("tr");
  for(const col of args.columns) {
    const th=node("th"), active=sort?.name===col.name;
    if(col.type==="number")th.className="number";
    th.scope="col"; th.setAttribute("aria-sort",active?(sort.direction===1?"ascending":"descending"):"none");
    const button=node("button",col.label+(active?(sort.direction===1?" ↑":" ↓"):""));button.type="button";button.title=col.help;
    button.onclick=()=>{sort={name:col.name,direction:active?-sort.direction:1};draw();};th.append(button);head.append(th);
  }
  $("thead").replaceChildren(head);const body=document.createDocumentFragment();
  for(const {row,index} of list.slice(page*size,(page+1)*size)) {
    const tr=node("tr");
    for(const col of args.columns) {
      const td=node("td"),value=row[col.name];if(typeof value==="number" || col.type==="number")td.className="number";
      if(col.format==="vn_signed_vnd" && Number.isFinite(Number(value))) {
        if(Number(value)>0)td.classList.add("positive");
        else if(Number(value)<0)td.classList.add("negative");
        else td.classList.add("neutral");
      }
      if(col.editable) {
        const input=node(col.type==="selectbox"?"select":"input");
        input.setAttribute("aria-label",`${col.label} · ${index+1}`);input.title=col.help;
        if(col.type==="selectbox")for(const option of col.options??[])input.append(node("option",option));
        else {input.type=col.type==="number"?"number":"text";if(input.type==="number") {input.step="any";if(col.min_value!=null)input.min=col.min_value;if(col.max_value!=null)input.max=col.max_value;}}
        input.value=value??"";input.required=col.required;input.disabled=!!args.disabled;
        input.addEventListener("input",()=>{rows[index][col.name]=input.value;input.setAttribute("aria-invalid",String(!input.checkValidity()));publish();});
        td.append(input);
      } else if(col.type==="link" && /^https?:\/\//i.test(String(value))) {
        const link=node("a",col.label);link.href=value;link.target="_blank";link.rel="noopener noreferrer";link.title=value;td.append(link);
      } else {
        td.textContent=format(value,col);
        if(col.type==="progress" && Number.isFinite(Number(value))) {
          const meter=node("div"),bar=node("span");meter.className="meter";
          const min=col.min_value??0,max=col.max_value??100;
          bar.style.width=`${Math.max(0,Math.min(100,100*(Number(value)-min)/(max-min||1)))}%`;meter.append(bar);td.append(meter);
        }
      }
      tr.append(td);
    }body.append(tr);
  }
  if(!list.length){const td=node("td",args.labels[5]);td.colSpan=Math.max(1,args.columns.length);const tr=node("tr");tr.append(td);body.append(tr);}
  $("tbody").replaceChildren(body);$("#count").textContent=`${list.length?page*size+1:0}–${Math.min((page+1)*size,list.length)} / ${list.length} ${args.labels[4]}`;
  $("#prev").disabled=page===0;$("#next").disabled=(page+1)*size>=list.length;height();
}
$("#search").oninput=e=>{query=e.target.value.toLocaleLowerCase();page=0;draw();};
$("#prev").onclick=()=>{page--;draw();};$("#next").onclick=()=>{page++;draw();};
$("#export").onclick=()=>{
  const cell=value=>{let s=String(value??"");if(/^[\s]*[=+@-]/.test(s)&&!/^[-+]?\d+(\.\d+)?$/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
  const csv=[args.columns.map(c=>cell(c.label)).join(","),...filtered().map(({row})=>args.columns.map(c=>cell(row[c.name])).join(","))].join("\r\n");
  const url=URL.createObjectURL(new Blob(["\ufeff",csv],{type:"text/csv;charset=utf-8"}));const a=node("a");a.href=url;a.download="market-table.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener("message",event=>{
  if(event.source!==parent || event.origin!==parentOrigin || event.data.type!=="streamlit:render")return;
  args={...event.data.args,disabled:event.data.disabled};
  for(const [key,value] of Object.entries(args.colors))document.documentElement.style.setProperty(`--${key}`,value);
  document.documentElement.style.colorScheme=args.light?"light":"dark";
  if(revision!==args.revision){revision=args.revision;rows=structuredClone(args.draft_rows??args.rows);page=0;}
  $("#search").placeholder=args.labels[0];$("#search").setAttribute("aria-label",args.labels[0]);
  $("#export").textContent=args.labels[1];$("#prev").textContent=args.labels[2];$("#next").textContent=args.labels[3];
  $(".scroll").style.maxHeight=`${args.max_height}px`;draw();
});
new ResizeObserver(height).observe(document.body);
send("streamlit:componentReady",{apiVersion:1});
