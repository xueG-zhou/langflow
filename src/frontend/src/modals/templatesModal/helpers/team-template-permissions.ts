import type { TemplateExample } from "@/types/templates/types";

interface TemplateUser {
  id?: string;
  username?: string;
  is_superuser?: boolean;
}

export function canDeleteTeamTemplate(
  template: TemplateExample,
  user: TemplateUser | null | undefined,
): boolean {
  return (
    template.source === "team" &&
    (template.created_by === user?.id ||
      (template.visibility === "PUBLIC" && user?.is_superuser === true))
  );
}
