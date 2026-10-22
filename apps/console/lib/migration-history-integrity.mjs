import {createHash} from "node:crypto";

const NAME=/^[a-z0-9_]{1,120}$/;
const VERSION=/^\d{14}$/;
const MAX_BYTES=1048576;

/** Pick exactly one remote version for the requested name. Unrelated legacy duplicates do not block. */
export function migrationVersionByName(payload,requestedName){
 if(typeof requestedName!=="string"||!NAME.test(requestedName))throw new Error("migration_name_invalid");
 const rows=Array.isArray(payload)?payload
  :Array.isArray(payload?.data)?payload.data
  :Array.isArray(payload?.migrations)?payload.migrations:null;
 if(!rows||rows.length>2000)throw new Error("migration_history_unverifiable");
 const matches=rows.filter(row=>row&&typeof row==="object"&&row.name===requestedName);
 if(matches.length>1)throw new Error("migration_name_ambiguous");
 if(matches.length===0)return null;
 const version=matches[0].version;
 if(typeof version!=="string"||!VERSION.test(version))throw new Error("migration_version_unverifiable");
 return version;
}

/** Require byte-for-byte evidence before treating an existing migration as applied. */
export function requireVerifiedMigrationSource(payload,{name,version,sql}){
 if(typeof name!=="string"||!NAME.test(name)
    ||typeof version!=="string"||!VERSION.test(version)
    ||typeof sql!=="string"||!sql.trim()
    ||Buffer.byteLength(sql,"utf8")>MAX_BYTES)throw new Error("migration_expectation_invalid");
 const row=payload&&typeof payload==="object"
  ?(payload.data&&typeof payload.data==="object"&&!Array.isArray(payload.data)
    ?payload.data:payload):null;
 if(!row||row.name!==name||row.version!==version)throw new Error("migration_applied_identity_mismatch");
 const statements=row.statements;
 if(!Array.isArray(statements)||statements.length<1||statements.length>64
    ||statements.some(x=>typeof x!=="string"||Buffer.byteLength(x,"utf8")>MAX_BYTES))
  throw new Error("migration_applied_source_unverifiable");
 // Exact concatenation only. No invented SQL separators, semantic guesses or
 // whitespace stripping; mismatched history must never resolve a human gate.
 if(statements.join("")!==sql)throw new Error("migration_applied_sql_mismatch");
 return{version,sqlSha256:createHash("sha256").update(sql,"utf8").digest("hex")};
}
