/* Distribución explícita de un comprobante, calculada en centavos. */
(function(root){
  function cents(value){
    const text=String(value??'').trim().replace(',','.');
    if(!/^\d+(?:\.\d{1,2})?$/.test(text))return null;
    const [whole,fraction='']=text.split('.');
    const result=Number(whole)*100+Number(fraction.padEnd(2,'0'));
    return Number.isSafeInteger(result)?result:null;
  }
  function validate(items,invoices,amount){
    const receipt=cents(amount),seen=new Set();let total=0;
    if(receipt===null||receipt<=0)return {valid:false,error:'El comprobante no tiene un importe válido.'};
    if(!items.length)return {valid:false,error:'Selecciona las facturas de este pago y revisa sus paquetes.'};
    for(const item of items){
      const invoice=invoices.find(f=>f.codigo===item.factura_codigo),value=cents(item.monto);
      if(!invoice||seen.has(item.factura_codigo))return {valid:false,error:'Revisa la selección de facturas.'};
      seen.add(item.factura_codigo);
      if(value===null||value<=0)return {valid:false,error:'Cada factura seleccionada necesita un importe mayor que cero, con hasta dos decimales.'};
      const balance=cents(invoice.saldo_pendiente);
      if(balance===null||value>balance)return {valid:false,error:'El importe supera el saldo de '+invoice.codigo+'.'};
      total+=value;
    }
    const remaining=receipt-total;
    if(remaining!==0)return {valid:false,total,error:remaining>0?'Falta asignar $'+(remaining/100).toFixed(2)+' del comprobante.':'Asignaste $'+(-remaining/100).toFixed(2)+' de más. Corrige la distribución.'};
    return {valid:true,total,error:''};
  }
  function read(container){return [...container.querySelectorAll('[data-invoice-code]')].filter(row=>row.querySelector('[type=checkbox]').checked).map(row=>({factura_codigo:row.dataset.invoiceCode,monto:row.querySelector('[data-allocation-amount]').value}));}
  function render(container,invoices,amount,disabled,escape,onChange){
    container.innerHTML=invoices.map((f,index)=>'<div class="allocation-row" data-invoice-code="'+escape(f.codigo)+'"><label class="allocation-choice"><input type="checkbox" '+(disabled?'disabled':'')+'><span><b>'+escape(f.codigo)+'</b><small>Saldo $'+Number(f.saldo_pendiente).toFixed(2)+'</small></span></label><label class="allocation-value">Aplicar $<input data-allocation-amount type="text" inputmode="decimal" maxlength="16" aria-label="Importe para '+escape(f.codigo)+'" placeholder="0.00" disabled></label><small class="allocation-packages">'+(f.paquetes||[]).map(p=>escape(p.tracking||'Sin tracking')).join('<br>')+'</small></div>').join('');
    container.onchange=e=>{
      const row=e.target.closest('[data-invoice-code]');if(!row)return;
      const checkbox=row.querySelector('[type=checkbox]'),input=row.querySelector('[data-allocation-amount]');
      if(e.target===checkbox){
        input.disabled=!checkbox.checked;
        if(checkbox.checked&&!input.value){
          const other=read(container).filter(x=>x.factura_codigo!==row.dataset.invoiceCode).reduce((sum,x)=>sum+(cents(x.monto)||0),0);
          const invoice=invoices.find(f=>f.codigo===row.dataset.invoiceCode);
          input.value=(Math.max(0,Math.min(cents(invoice.saldo_pendiente)||0,(cents(amount)||0)-other))/100).toFixed(2);
        }
      }
      onChange();
    };
    container.oninput=()=>onChange();
  }
  root.CubicoPaymentAllocation={cents,validate,read,render};
  if(typeof module!=='undefined')module.exports=root.CubicoPaymentAllocation;
})(typeof window!=='undefined'?window:globalThis);
