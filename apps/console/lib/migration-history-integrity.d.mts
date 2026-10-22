export function migrationVersionByName(payload:unknown,requestedName:string):string|null;
export function requireVerifiedMigrationSource(
 payload:unknown,expected:{name:string;version:string;sql:string}
):{version:string;sqlSha256:string};
