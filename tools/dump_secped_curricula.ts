// Exporta os moldes curriculares do secPed-Express para docs/referencias/academico/curriculos-secped.json.
// Uso (na pasta secPed-Express/apps/api): TS_NODE_TRANSPILE_ONLY=1 TS_NODE_COMPILER_OPTIONS='{"module":"commonjs"}' \
//   ../../node_modules/.bin/ts-node <caminho>/tools/dump_secped_curricula.ts > <caminho>/docs/referencias/academico/curriculos-secped.json
const B = '/Users/vadao/Projectos_Next/secPed-Express/apps/api';
const p = require(B + '/prisma/templates/primario');
const m = require(B + '/prisma/templates/magisterio');
const t = require(B + '/prisma/templates/tecnico');
const s = require(B + '/prisma/templates/secundario');
const c = require(B + '/src/shared/constants/angola-subject-codes');
const templates = [p.PRIMARIO_BASE, s.SECUNDARIO_I_BASE, s.SECUNDARIO_II_BASE, s.SEC2_CFB, s.SEC2_CEJ, s.SEC2_CH, s.SEC2_AV,
  m.MAGISTERIO_BASE, m.MAGISTERIO_PRIMARIO, t.TECNICO_BASE, t.TECNICO_INFOGEST, t.TECNICO_CONTAB, t.TECNICO_SAUDE,
  t.TECNICO_ANALISES, t.TECNICO_ELET, t.TECNICO_CONST, t.TECNICO_SECR, t.TECNICO_INFO, t.TECNICO_MEC, t.TECNICO_AGRO, t.TECNICO_HOT];
const codes = new Set<string>();
templates.forEach((x: any) => x.years.forEach((y: any) => y.subjects.forEach((z: any) => codes.add(z.code))));
const names: Record<string, string> = {};
codes.forEach((k) => (names[k] = c.subjectName(k)));
console.log(JSON.stringify({ templates, names, catalog: c.ANGOLA_SUBJECT_CODES ?? null }, null, 1));
