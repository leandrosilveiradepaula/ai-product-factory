import test from "node:test";
import assert from "node:assert/strict";
import {migrationVersionByName,requireVerifiedMigrationSource} from "../lib/migration-history-integrity.mjs";

const name="ci_repair_cumulative_scopes";
const version="20261022141432";
const sql="begin;\nselect 1;\ncommit;\n";
const row={version,name,statements:[sql]};

test("generated Supabase version may differ from Git filename if SQL matches",()=>{
 assert.equal(migrationVersionByName({migrations:[row]},name),version);
 const proof=requireVerifiedMigrationSource(row,{name,version,sql});
 assert.equal(proof.version,version);
 assert.match(proof.sqlSha256,/^[0-9a-f]{64}$/);
});
test("unrelated legacy duplicate names do not hide exact target",()=>{
 assert.equal(migrationVersionByName({data:[
  {name:"legacy_dup",version:"20261021111111"},
  {name:"legacy_dup",version:"20261021111112"},row,
 ]},name),version);
});
test("nonexistent target is not a positive applied result",()=>{
 assert.equal(migrationVersionByName([],name),null);
});
test("same migration name with two versions blocks reconciliation",()=>{
 assert.throws(()=>migrationVersionByName([row,{...row,version:"20261022141433"}],name),/migration_name_ambiguous/);
});
test("malformed or incomplete history fails closed",()=>{
 for(const source of [{unexpected:[]},{data:"bogus"},null])
  assert.throws(()=>migrationVersionByName(source,name),/migration_history_unverifiable/);
 assert.throws(()=>migrationVersionByName([{...row,version:"bad"}],name),/migration_version_unverifiable/);
});
test("same name/version with different SQL cannot resolve an applied gate",()=>{
 assert.throws(()=>requireVerifiedMigrationSource({...row,statements:["drop table public.data;"]},{name,version,sql}),/migration_applied_sql_mismatch/);
});
test("comments, whitespace and line endings remain part of SQL identity",()=>{
 for(const content of [sql.trim(),sql.replaceAll("\n","\r\n"),sql+"\n"])
  assert.throws(()=>requireVerifiedMigrationSource({...row,statements:[content]},{name,version,sql}),/migration_applied_sql_mismatch/);
});
test("split or missing migration SQL is not fabricated into a receipt",()=>{
 for(const statements of [[],null,["begin;","select 1;","commit;"],[sql,3]])
  assert.throws(()=>requireVerifiedMigrationSource({...row,statements},{name,version,sql}),/migration_applied_source_unverifiable|migration_applied_sql_mismatch/);
});
test("wrong identity and oversized SQL cannot pass",()=>{
 assert.throws(()=>requireVerifiedMigrationSource({...row,version:"20261022125100"},{name,version,sql}),/identity_mismatch/);
 assert.throws(()=>requireVerifiedMigrationSource({data:{...row,name:"other"}},{name,version,sql}),/identity_mismatch/);
 assert.throws(()=>requireVerifiedMigrationSource(row,{name,version,sql:"x".repeat(1048577)}),/expectation_invalid/);
});
test("two exactly contiguous statements retain byte identity",()=>{
 const proof=requireVerifiedMigrationSource({...row,statements:[sql.slice(0,7),sql.slice(7)]},{name,version,sql});
 assert.equal(proof.version,version);
});
