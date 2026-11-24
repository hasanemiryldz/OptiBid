export function emsalForm(config, back, app){
 const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text||"";return n};
 const f=el("form");const fields={};
 const section=el("section");app.replaceChildren(el("h1","Emsal fiyatı ekle"),section);section.append(f);
 function field(key,label,options,value=""){
   const wrap=el("label",label);
   const input=el(options?"select":"input");
   if(options)for(const name of options){const option=el("option",name);option.value=name;input.append(option)}
   input.value=value||options?.[0]||"";input.required=true;
   fields[key]=input;wrap.append(input);f.append(wrap);return input
 }
 const type=field("tur","İhale türü",Object.keys(config.turler));
 const cat=field("ana","Ana kategori",[]);
 const sub=field("alt","Alt kategori",[]);
 const techBox=el("fieldset");
 function options(select,values){select.replaceChildren(...values.map(x=>el("option",x)))}
 function technical(){
   techBox.replaceChildren();const keys=config.turler[type.value]?.[cat.value]?.[sub.value]??[];
   keys.forEach(key=>{
     const l=el("label",key), i=el("input");i.name=key;l.append(i);techBox.append(l)
   })
 }
 function subs(){options(sub,Object.keys(config.turler[type.value][cat.value]));technical()}
 function categories(){options(cat,Object.keys(config.turler[type.value]));subs()}
 type.onchange=categories;cat.onchange=subs;sub.onchange=technical;categories();f.append(techBox);
 field("ikn","İKN");field("kaynak","Resmî ilan veya sonuç bağlantısı").type="url";
 field("tarih","Fiyatın dayandığı ihale tarihi").type="date";
 field("miktar","Kaynak miktar");field("birim","Kaynak birim",config.birimler);
 field("fiyat","Sözleşme bedeli");field("fiyat_turu","Bedel türü",["sözleşme toplamı","sözleşme birim"]);
 field("ulke","Ülke kodu",null,"TR");field("para","Para birimi",null,"TRY");
 field("kdv","KDV esası",["belirsiz","hariç","dahil"]);
 const verify=el("label","Tek kalemi, teknik bilgileri ve sözleşme fiyatını kaynakta doğruladım.");
 const check=el("input");check.type="checkbox";check.required=true;verify.append(check);f.append(verify);
 const save=el("button","Emsali kaydet");const cancel=el("button","Ana ekran");cancel.type="button";cancel.onclick=back;
 const nav=el("nav");nav.append(save,cancel);f.append(nav);
 const status=el("p");status.setAttribute("role","status");f.append(status);
 f.onsubmit=async event=>{
   event.preventDefault();save.disabled=true;
   const row=Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,input.value.trim()]));
   row.kategori=[row.ana,row.alt];row.dogrulandi=check.checked;
   row.teknik=Object.fromEntries([...techBox.querySelectorAll("input")].map(i=>[i.name,i.value.trim()||null]));
   try{
     const res=await fetch("/api/emsal-ekle",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(row)});
     const value=await res.json();
     if(!res.ok)throw Error(value.hata||"Emsal kaydedilemedi.");
     await back();document.querySelector("#notice").textContent="Emsal incelemeye alındı. Hesaba katılması için EKAP alan dayanakları doğrulanmalı.";
   }catch(e){status.textContent=e.message;save.disabled=false}
 };
}

