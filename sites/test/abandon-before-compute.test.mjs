import assert from 'node:assert/strict';
import test from 'node:test';
import {reserve, activate, release, reservation} from '../worker/admission.js';
import {setup} from './runtime.mjs';

test('lost activation acknowledgements: confirmed non-start revokes only own fence', async t=>{
 const {mf,db}=await setup();t.after(()=>mf.dispose());
 const active=()=>db.prepare('SELECT count(*) n FROM lab_admission WHERE active=1').first('n');
 const item=reservation('own-uncertain');assert.equal((await reserve(db,item)).status,200);
 const fault={prepare:db.prepare.bind(db),async batch(stmts){await db.batch(stmts);throw Error('lost acknowledgement')}};
 assert.equal((await activate(fault,item)).status,503);assert.equal(await active(),0);
 assert.equal((await activate(db,item)).status,429);
 const other=reservation('other');assert.equal((await reserve(db,other)).status,200);
 const holder=await activate(db,other);assert.equal(holder.status,200);
 assert.equal((await activate(fault,other)).status,503);assert.equal(await active(),1);
 assert.equal(await release(db,other.lease,'wrong-fence'),false);assert.equal(await holder.release(),true);
});

test('a persistent outage preserves RUNNING; delayed activation cannot cross cancellation', async t=>{
 const {mf,db}=await setup();t.after(()=>mf.dispose());
 const item=reservation('delayed');assert.equal((await reserve(db,item)).status,200);const delayed=[];
 const fault={prepare:db.prepare.bind(db),async batch(stmts){delayed.push(stmts);throw Error('delayed transport')}};
 assert.equal((await activate(fault,item)).status,503);
 for(const stmts of delayed)await db.batch(stmts);
 assert.equal(await db.prepare('SELECT active FROM lab_admission WHERE lease=?').bind(item.lease).first('active'),0);
 const second=reservation('unavailable');assert.equal((await reserve(db,second)).status,200);
 const unavailable={prepare(sql){const stmt=db.prepare(sql);if(!sql.includes('SET active=0, reserved_until=NULL'))return stmt;return {bind(){return {async run(){throw Error('D1 unreachable')}}}}},async batch(stmts){await db.batch(stmts);throw Error('lost reply')}};
 assert.equal((await activate(unavailable,second)).status,503);
 assert.equal(await db.prepare('SELECT active FROM lab_admission WHERE lease=?').bind(second.lease).first('active'),1);
});
