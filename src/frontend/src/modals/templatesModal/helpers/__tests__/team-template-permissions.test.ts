import type { TemplateExample } from "@/types/templates/types";
import { canDeleteTeamTemplate } from "../team-template-permissions";

const template = {
  id: "template-1",
  name: "Template",
  description: "Description",
  data: null,
  source: "team",
  created_by: "owner-1",
  visibility: "PRIVATE",
} as TemplateExample;

describe("canDeleteTeamTemplate", () => {
  it("does not allow a superuser to delete another user's private template", () => {
    expect(
      canDeleteTeamTemplate(template, {
        id: "another-user",
        username: "admin",
        is_superuser: true,
      }),
    ).toBe(false);
  });

  it("does not grant a named user special access", () => {
    expect(
      canDeleteTeamTemplate(template, {
        id: "another-user",
        username: "langflow",
        is_superuser: false,
      }),
    ).toBe(false);
  });

  it("does not allow an unrelated regular user", () => {
    expect(
      canDeleteTeamTemplate(template, {
        id: "another-user",
        username: "regular-user",
        is_superuser: false,
      }),
    ).toBe(false);
  });

  it("allows the owner to delete their template", () => {
    expect(
      canDeleteTeamTemplate(template, {
        id: "owner-1",
        username: "owner",
        is_superuser: false,
      }),
    ).toBe(true);
  });

  it("allows a superuser to manage a public template", () => {
    expect(
      canDeleteTeamTemplate(
        { ...template, visibility: "PUBLIC" },
        {
          id: "another-user",
          username: "admin",
          is_superuser: true,
        },
      ),
    ).toBe(true);
  });
});
