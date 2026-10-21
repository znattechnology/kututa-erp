"""Gera os moldes curriculares nacionais do edu_core a partir do catálogo do secPed-Express.

Fonte: docs/referencias/academico/curriculos-secped.json, exportado de secPed-Express/apps/api/prisma/templates com
tools/dump_secped_curricula.ts. Saída: custom_addons/edu_core/data/edu_curriculum_template_data.xml.

Uso: python3 tools/gen_edu_curricula.py
"""

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs/referencias/academico/curriculos-secped.json'
TARGET = ROOT / 'custom_addons/edu_core/data/edu_curriculum_template_data.xml'

LEVELS = {
    'INICIACAO': 'level_iniciacao',
    'PRIMARIO': 'level_primario',
    'SECUNDARIO_I_CICLO': 'level_sec1',
    'SECUNDARIO_II_CICLO': 'level_sec2',
    'TECNICO': 'level_tecnico',
    'MAGISTERIO': 'level_magisterio',
}
COMPONENTS = {
    'SOCIO_CULTURAL': 'socio_cultural',
    'CIENTIFICA': 'scientific',
    'TECNICA_PRATICA': 'technical',
    'ESTAGIO': 'internship',
}


def xmlid(*parts):
    return '_'.join(str(p).lower().replace('-', '_') for p in parts)


def field(name, value):
    return f'        <field name="{name}">{escape(str(value))}</field>'


def main():
    data = json.loads(SOURCE.read_text())
    names = data['names']
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!-- Gerado por tools/gen_edu_curricula.py a partir do catálogo do secPed-Express. Não editar à mão. -->',
        '<odoo>',
    ]
    for template in data['templates']:
        tid = xmlid('tpl', template['code'])
        out += [
            f'    <record id="{tid}" model="edu.curriculum.template">',
            field('code', template['code']),
            field('name', template['name']),
        ]
        if template.get('description'):
            out.append(field('description', template['description']))
        out += [
            f'        <field name="level_id" ref="{LEVELS[template["level"]]}"/>',
            f'        <field name="is_profile" eval="{bool(template["profileCode"])}"/>',
            field('version', template.get('version') or 1),
            '    </record>',
        ]
        for year in template['years']:
            yid = xmlid(tid, 'y', year['year'])
            out += [
                f'    <record id="{yid}" model="edu.curriculum.template.year">',
                f'        <field name="template_id" ref="{tid}"/>',
                field('year', year['year']),
                field('class_number', year['classNumber']),
            ]
            if year.get('name'):
                out.append(field('name', year['name']))
            out.append('    </record>')
            for sequence, subject in enumerate(year['subjects'], start=1):
                out += [
                    f'    <record id="{xmlid(yid, subject["code"])}" model="edu.curriculum.template.line">',
                    f'        <field name="year_id" ref="{yid}"/>',
                    field('sequence', sequence),
                    field('subject_code', subject['code']),
                    field('name', names.get(subject['code'], subject['code'])),
                    field('weekly_hours', subject['weeklyHours']),
                ]
                if subject.get('component'):
                    out.append(field('component', COMPONENTS[subject['component']]))
                out += [
                    field('duration_years', subject.get('durationYears', 1)),
                    field('start_year', subject.get('startYear', 1)),
                    f'        <field name="is_compulsory" eval="{subject.get("isCompulsory", True)}"/>',
                    f'        <field name="is_national_exam" eval="{subject.get("isNationalExam", False)}"/>',
                    '    </record>',
                ]
    out.append('</odoo>\n')
    TARGET.write_text('\n'.join(out))
    print(f'{TARGET.relative_to(ROOT)}: {len(data["templates"])} moldes')


if __name__ == '__main__':
    main()
