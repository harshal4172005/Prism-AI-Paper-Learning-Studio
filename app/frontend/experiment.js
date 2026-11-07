/* Seeded numerical illustration; no model training or fabricated measurements. */
(function () {
  function randomGenerator(seed) {
    let state = seed >>> 0;
    return () => {state += 0x6D2B79F5; let t = state; t = Math.imul(t ^ t >>> 15,t | 1); t ^= t + Math.imul(t ^ t >>> 7,t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296;};
  }
  function softmax(values) {
    const max = Math.max(...values), weights = values.map(value=>Math.exp(value-max));
    const total = weights.reduce((a,b)=>a+b,0);return weights.map(value=>value/total);
  }
  function entropy(weights) {return -weights.reduce((sum,p)=>sum+(p>0?p*Math.log(p):0),0)/Math.log(weights.length);}
  function simulate(dimension, seed, count=8) {
    if(!Number.isInteger(dimension)||dimension<1||dimension>4096||!Number.isInteger(count)||count<2||count>100)throw new Error("Invalid experiment size");
    const random=randomGenerator(seed);
    const normal=()=>Math.sqrt(-2*Math.log(Math.max(random(),1e-12)))*Math.cos(2*Math.PI*random());
    const query=Array.from({length:dimension},normal);
    const logits=Array.from({length:count},()=>query.reduce((sum,q)=>sum+q*normal(),0));
    const raw=softmax(logits),scaled=softmax(logits.map(value=>value/Math.sqrt(dimension)));
    return {dimension,seed,key_count:count,logits,raw,scaled,raw_entropy:entropy(raw),scaled_entropy:entropy(scaled),
      description:"Untrained standard-normal query/key vectors. A numerical illustration, not trained-model performance or a gradient measurement."};
  }
  if(typeof module!=="undefined"&&module.exports)module.exports={simulate,softmax,entropy};
  if(typeof document==="undefined")return;
  const $=id=>document.getElementById(id),dimensions=[4,16,64,128,256,512];let latest;
  function chart(id,weights) {
    const root=$(id);root.replaceChildren();
    weights.forEach((weight,index)=>{const bar=document.createElement("div");bar.className="bar";bar.style.height=(weight*100)+"%";bar.title="Key "+(index+1)+": "+(weight*100).toFixed(2)+"%";
      const label=document.createElement("span");label.textContent=String(index+1);bar.append(label);root.append(bar);});
    root.setAttribute("aria-label",weights.map((weight,index)=>"Key "+(index+1)+": "+(weight*100).toFixed(1)+" percent").join(", "));
  }
  function update() {
    const dimension=dimensions[Number($("dimension").value)],seed=Math.max(1,Math.min(999999,Math.trunc(Number($("seed").value)||42)));
    $("seed").value=seed;$("dimension-value").textContent=dimension;latest=simulate(dimension,seed);
    chart("raw-chart",latest.raw);chart("scaled-chart",latest.scaled);
    const rawPeak=Math.max(...latest.raw)*100,scaledPeak=Math.max(...latest.scaled)*100;
    $("raw-peak").textContent="Peak "+rawPeak.toFixed(1)+"%";$("scaled-peak").textContent="Peak "+scaledPeak.toFixed(1)+"%";
    $("raw-entropy").textContent="Spread (normalized entropy): "+latest.raw_entropy.toFixed(3);
    $("scaled-entropy").textContent="Spread (normalized entropy): "+latest.scaled_entropy.toFixed(3);
    $("lab-result").textContent="In this sample, the strongest key receives "+rawPeak.toFixed(1)+"% of the attention without scaling and "+scaledPeak.toFixed(1)+"% with scaling. Dividing by √"+dimension+" makes the distribution less concentrated. Try another seed to see how the example varies.";
  }
  $("dimension").addEventListener("input",update);$("seed").addEventListener("change",update);
  $("resample").addEventListener("click",()=>{$("seed").value=(Number($("seed").value)%999999)+1;update();});
  $("export-lab").addEventListener("click",()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(latest,null,2)],{type:"application/json"}));const link=document.createElement("a");link.href=url;link.download="attention-scaling-measurements.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  update();
})();
