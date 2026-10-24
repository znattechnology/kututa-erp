import { mobileTabs } from "@edu_roles/mobile_tabs/mobile_tabs";

// O aluno no telemóvel, como no secPed: o painel, as notas, o horário e as provas (o resto fica no «Menu»).
mobileTabs.add("student", {
    app: "edu_portal.menu_student_root",
    tabs: [
        { label: "Painel", icon: "home", action: "edu_portal.action_student_home", tag: "edu_portal.student_home" },
        { label: "Notas", icon: "school", action: "edu_portal.action_student_grades", tag: "edu_portal.student_grades" },
        { label: "Horário", icon: "calendar_month", action: "edu_portal.action_student_schedule", tag: "edu_portal.student_schedule" },
        { label: "Provas", icon: "edit_note", action: "edu_portal.action_student_exams", tag: "edu_portal.student_exams" },
    ],
});
