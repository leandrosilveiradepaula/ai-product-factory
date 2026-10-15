"""Repository onboarding must be an explicit, fail-closed admin operation."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
ROUTE=(ROOT/"apps/console/app/api/projects/[key]/link-repository/route.ts").read_text()
APP=(ROOT/"apps/console/lib/github-app.ts").read_text()
PAGE=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()

class GreenfieldRepositoryLinkingTests(unittest.TestCase):
 def test_admin_post_same_origin_and_expected_repository(self):
  self.assertIn("export async function POST(",ROUTE)
  self.assertIn("await requireConsoleAdmin()",ROUTE)
  self.assertIn('request.headers.get("origin")!==url.origin',ROUTE)
  self.assertIn('application/x-www-form-urlencoded',ROUTE)
  self.assertIn('project.kind!=="greenfield"',ROUTE)
  self.assertIn('const expected="leandrosilveiradepaula/"+key',ROUTE)
  self.assertIn("conflicts.some(x=>x.id!==project.id)",ROUTE)
  self.assertIn("&repository=is.null&project_kind=eq.greenfield",ROUTE)
  self.assertIn("inspectPrivateProjectRepositoryBeforeLink(expected)",ROUTE)
  self.assertLess(ROUTE.index("inspectPrivateProjectRepositoryBeforeLink(expected)"),ROUTE.index('method:"PATCH"'))
  self.assertIn('verifyProjectGitHubApp(key)',ROUTE)
  self.assertNotIn('update_ref',ROUTE)
  self.assertNotIn('run_direct',ROUTE)

 def test_probe_fails_closed_and_does_not_expose_token(self):
  part=APP.split("export async function inspectPrivateProjectRepositoryBeforeLink(",1)[1].split("/**",1)[0]
  self.assertIn("getGitHubAppCredentials()",part)
  self.assertIn("createAppJwt(",part)
  self.assertIn("repositories:[name],permissions:APP_PERMISSIONS",part)
  self.assertIn("permissionAllowsWrite(perms.contents)",part)
  self.assertIn("permissionAllowsWrite(perms.issues)",part)
  self.assertIn("permissionAllowsWrite(perms.pull_requests)",part)
  self.assertIn("metadata?.private!==true",part)
  self.assertIn('metadata?.default_branch!=="main"',part)
  self.assertIn("metadata?.archived===true",part)
  self.assertIn("/git/ref/heads/main",part)
  self.assertNotIn("return{token",part)
  self.assertNotIn("/user/repos",part)
  self.assertNotIn("/orgs/",part)

 def test_ui_requires_explicit_operator_repo_and_installation_actions(self):
  self.assertIn('id="repository-setup"',PAGE)
  self.assertIn('!p.repository&&p.kind==="greenfield"',PAGE)
  self.assertIn('https://github.com/new?name=',PAGE)
  self.assertIn('https://github.com/settings/installations',PAGE)
  self.assertIn('operator.role==="admin"?<form method="POST"',PAGE)
  self.assertIn('"link-repository"',PAGE)
  self.assertIn('"repo_link"',PAGE.replace('query.repo_link','"repo_link"'))
  self.assertIn('Nenhuma alteração foi feita.',PAGE)

if __name__=="__main__":
 unittest.main()
