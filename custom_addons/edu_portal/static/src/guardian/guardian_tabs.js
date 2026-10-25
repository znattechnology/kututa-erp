import { mobileTabs } from "@edu_roles/mobile_tabs/mobile_tabs";

// O encarregado no telemóvel, como no secPed: o painel, as notas, as faltas e as propinas (o resto fica no «Menu»).
mobileTabs.add("guardian", {
    app: "edu_portal.menu_guardian_root",
    tabs: [
        { label: "Painel", icon: "home", action: "edu_portal.action_guardian_home", tag: "edu_portal.guardian_home" },
        { label: "Notas", icon: "school", action: "edu_portal.action_guardian_grades", tag: "edu_portal.guardian_grades" },
        { label: "Faltas", icon: "person_off", action: "edu_portal.action_guardian_absences", tag: "edu_portal.guardian_absences" },
        { label: "Propinas", icon: "payments", action: "edu_portal.action_guardian_fees", tag: "edu_portal.guardian_fees" },
    ],
});
