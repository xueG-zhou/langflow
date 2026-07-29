import axios from "axios";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import { useGetSkills, usePostSkill } from "@/controllers/API/queries/skills";
import useAlertStore from "@/stores/alertStore";
import { cn } from "@/utils/utils";

const MAX_SKILL_SIZE = 25 * 1024 * 1024;

export default function SkillsPage() {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const { data: skills, isLoading } = useGetSkills();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const { mutate: uploadSkill, isPending } = usePostSkill();

  const showError = (message: string) => {
    setErrorData({
      title: t("settings.skills.uploadFailed", {
        defaultValue: "Skill upload failed",
      }),
      list: [message],
    });
  };

  const handleFile = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      showError(
        t("settings.skills.zipOnly", {
          defaultValue: "Select a ZIP archive containing one Skill.",
        }),
      );
      return;
    }
    if (file.size > MAX_SKILL_SIZE) {
      showError(
        t("settings.skills.tooLarge", {
          defaultValue: "The ZIP archive must be 25 MB or smaller.",
        }),
      );
      return;
    }

    uploadSkill(file, {
      onSuccess: (skill) => {
        setSuccessData({
          title: t("settings.skills.uploadSuccess", {
            defaultValue: "{{name}} installed successfully",
            name: skill.name,
          }),
        });
        if (inputRef.current) inputRef.current.value = "";
      },
      onError: (error: unknown) => {
        showError(
          (axios.isAxiosError(error) && error.response?.data?.detail) ||
            (error instanceof Error && error.message) ||
            t("errors.generic"),
        );
      },
    });
  };

  return (
    <div className="flex h-full w-full flex-col gap-6">
      <div className="flex flex-col">
        <h2
          className="flex items-center text-lg font-semibold tracking-tight"
          data-testid="settings_menu_header"
        >
          {t("settings.skills.title", { defaultValue: "Skills" })}
          <ForwardedIconComponent
            name="PackageOpen"
            className="ml-2 h-5 w-5 text-primary"
          />
        </h2>
        <p className="text-sm text-muted-foreground">
          {t("settings.skills.description", {
            defaultValue:
              "Install Skills from ZIP archives and view the Skills available to Langflow.",
          })}
        </p>
      </div>

      <section aria-labelledby="upload-skill-heading">
        <h3 id="upload-skill-heading" className="mb-2 text-sm font-medium">
          {t("settings.skills.uploadTitle", { defaultValue: "Upload a Skill" })}
        </h3>
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          onChange={(event) => handleFile(event.target.files?.[0])}
          data-testid="skill-file-input"
        />
        <button
          type="button"
          disabled={isPending}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            event.preventDefault();
            setIsDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragging(false);
            handleFile(event.dataTransfer.files[0]);
          }}
          className={cn(
            "flex min-h-44 w-full cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 px-6 py-8 text-center transition-colors",
            "hover:border-primary/60 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            isDragging && "border-primary bg-accent/60",
            isPending && "cursor-wait opacity-60",
          )}
          aria-label={t("settings.skills.chooseZip", {
            defaultValue: "Choose a Skill ZIP archive",
          })}
        >
          {isPending ? (
            <Loading />
          ) : (
            <ForwardedIconComponent
              name="FileArchive"
              className="mb-3 h-8 w-8 text-muted-foreground"
            />
          )}
          <span className="text-sm font-medium">
            {isPending
              ? t("settings.skills.installing", {
                  defaultValue: "Installing Skill…",
                })
              : t("settings.skills.dropZip", {
                  defaultValue: "Drop a Skill ZIP here, or click to browse",
                })}
          </span>
          <span className="mt-1 text-xs text-muted-foreground">
            {t("settings.skills.requirements", {
              defaultValue:
                "Maximum 25 MB. The archive must contain a root SKILL.md file.",
            })}
          </span>
        </button>
      </section>

      <section
        className="flex min-h-0 flex-1 flex-col"
        aria-labelledby="installed-skills-heading"
      >
        <h3 id="installed-skills-heading" className="mb-2 text-sm font-medium">
          {t("settings.skills.installed", {
            defaultValue: "Installed Skills",
          })}
        </h3>
        {isLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <Loading />
          </div>
        ) : skills?.length ? (
          <div className="flex flex-col gap-1">
            {skills.map((skill) => (
              <div
                key={skill.name}
                className="flex items-start gap-3 rounded-lg border bg-muted/30 px-4 py-3"
              >
                <ForwardedIconComponent
                  name="PackageCheck"
                  className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary"
                />
                <div className="min-w-0">
                  <div className="text-sm font-medium">{skill.name}</div>
                  <p className="mt-0.5 text-sm text-muted-foreground">
                    {skill.description ||
                      t("settings.skills.noDescription", {
                        defaultValue: "No description provided.",
                      })}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
            <ForwardedIconComponent
              name="PackageOpen"
              className="mb-3 h-8 w-8 text-muted-foreground"
            />
            <p className="text-sm font-medium">
              {t("settings.skills.empty", {
                defaultValue: "No Skills installed yet",
              })}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => inputRef.current?.click()}
            >
              <ForwardedIconComponent name="Upload" className="h-4 w-4" />
              {t("settings.skills.uploadFirst", {
                defaultValue: "Upload your first Skill",
              })}
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
