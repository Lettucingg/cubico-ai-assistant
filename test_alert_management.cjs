const assert=require('node:assert/strict');
const {collect,filter}=require('./app/static/alert-management.js');
const c={telefono:'507',nombre:'Cliente',tiene_no_leidos:true,ultimo_mensaje_cliente:{id:1,timestamp:'2026-10-02',contenido:'Hola'}};
const key=collect([c],[],[])[0].clave;
assert.equal(collect([{...c,actualizado_en:'later',ultimo_mensaje:{id:3}}],[],[])[0].clave,key);
assert.notEqual(collect([{...c,ultimo_mensaje_cliente:{...c.ultimo_mensaje_cliente,id:2}}],[],[])[0].clave,key);
const human={...c,necesita_atencion_humana:true,motivo_escalamiento:'Revisar paquete'};
assert.equal(collect([human],[],[]).length,1);
assert.notEqual(collect([human],[],[])[0].clave,key);
assert.notEqual(collect([{...human,motivo_escalamiento:'Otro caso'}],[],[])[0].clave,collect([human],[],[])[0].clave);
assert.equal(collect([{...c,ultimo_mensaje:{id:3,estado_entrega:'failed'}}],[],[]).length,2);
const s={telefono:'507',nombre:'Cliente',tipo:'domicilio',pago_reportado:true,pago_confirmado:false,actualizado_en:'a'};
assert.equal(collect([],[s],[]).length,2);
assert.notEqual(collect([],[s],[])[0].clave,collect([],[{...s,actualizado_en:'b'}],[])[0].clave);
assert.equal(collect([],[{...s,pago_confirmado:true,direccion:'Calle 1'}],[]).length,0);
assert.equal(collect([],[],[{id:1,estado:'ganada'}]).length,0);
const long=collect([{...human,motivo_escalamiento:'x'.repeat(4000),ultimo_mensaje_cliente:{contenido:'x'.repeat(4000),timestamp:'x'.repeat(4000)}}],[],[])[0];
assert.ok(long.clave.length<=2000);assert.ok(long.titulo.length<=300);assert.ok(long.descripcion.length<=500);
console.log('Alert identities: passed');

const all=collect([c,human],[s],[{id:1,estado:'nueva',empresa:'Arthur'}]);
assert.equal(filter(all,'arthur','negocios').length,1);
assert.equal(filter(all,'arthur','pagos').length,0);
assert.equal(filter(all,'  CLIENTE  ','equipo').length,2);
assert.equal(filter(all,'','all').length,all.length);
console.log('Alert search and category filters: passed');
const {context,detail}=require('./app/static/alert-management.js');
for(const kind of ['malid','demora_miami','pago','direccion','fallido','oportunidad','humano']){
 const ctx=context({kind,descripcion:'Motivo real'},c);
 assert.ok(ctx.pasos.length);assert.ok(ctx.borrador);assert.equal(ctx.ultimo_cliente.texto,'Hola');
 assert.match(detail(ctx),/Qué hacer/);
}
const structured={categoria:'Paquete mal identificado',motivo:'<script>bad()</script>',pasos:['<img src=x>'],borrador:'No enviado',nota:'Interno'};
const enriched=collect([{...human,contexto_atencion:structured}],[],[])[0];
assert.equal(enriched.contexto,structured);assert.match(detail(structured),/&lt;script&gt;/);assert.ok(!detail(structured).includes('<script>'));
assert.equal(filter([enriched],'paquete mal identificado').length,1);
console.log('Actionable guides, real quotes, search and HTML escaping: passed');
