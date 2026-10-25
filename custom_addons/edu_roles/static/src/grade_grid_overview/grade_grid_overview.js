import { GradeGrid } from "@edu_evaluation/grade_grid/grade_grid";
import { patch } from "@web/core/utils/patch";

/**
 * «Turmas e notas» com o resumo da pauta em gráficos, como nos painéis: em cima, a média, as positivas, as negativas e
 * quem está sem classificação (da classificação final quando já há, senão do último trimestre com notas); por baixo da
 * grelha, cada trimestre e a classificação final em barras empilhadas.
 */
patch(GradeGrid.prototype, {
    get overview() {
        const summary = this.state.data?.summary;
        if (!summary?.terms) {
            return null;
        }
        const pass = this.state.data.policy.pass_grade;
        const finalGraded = summary.positives + summary.negatives;
        const terms = summary.terms.map((t) => ({
            ...t,
            key: `t${t.id}`,
            graded: t.positives + t.negatives,
            averagePos: t.average !== null && t.average >= pass,
        }));
        const rows = [
            ...terms,
            {
                key: "final",
                name: "Classificação final",
                positives: summary.positives,
                negatives: summary.negatives,
                missing: summary.without_final,
                average: summary.average,
                averagePos: summary.average !== null && summary.average >= pass,
                graded: finalGraded,
                final: true,
            },
        ];
        const focus = finalGraded
            ? rows.at(-1)
            : [...terms].reverse().find((t) => t.graded) || terms.find((t) => t.is_current) || terms[0];
        return { enrolled: summary.enrolled, focus, rows };
    },
});
