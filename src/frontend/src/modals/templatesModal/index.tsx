import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { SidebarProvider } from "@/components/ui/sidebar";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { track } from "@/customization/utils/analytics";
import useAddFlow from "@/hooks/flows/use-add-flow";
import type { Category } from "@/types/templates/types";
import { cn } from "@/utils/utils";
import type { newFlowModalPropsType } from "../../types/components";
import BaseModal from "../baseModal";
import { Nav } from "./components/navComponent";
import TemplateContentComponent from "./components/TemplateContentComponent";

export default function TemplatesModal({
  open,
  setOpen,
}: newFlowModalPropsType): JSX.Element {
  const { t } = useTranslation();
  const [currentTab, setCurrentTab] = useState("all-templates");
  const [loading, setLoading] = useState(false);
  const addFlow = useAddFlow();
  const navigate = useCustomNavigate();
  const { folderId } = useParams();
  const handleFlowCreating = (isCreating: boolean) => {
    setLoading(isCreating);
  };

  const handleCreateBlankFlow = () => {
    if (loading) return;

    handleFlowCreating(true);
    track("New Flow Created", { template: "Blank Flow" });

    addFlow()
      .then((id) => {
        navigate(`/flow/${id}${folderId ? `/folder/${folderId}` : ""}`);
      })
      .finally(() => {
        handleFlowCreating(false);
      });
  };

  // Define categories and their items
  const categories: Category[] = [
    {
      title: t("templatesModal.title"),
      items: [
        {
          title: t("templatesModal.allTemplates"),
          icon: "LayoutPanelTop",
          id: "all-templates",
        },
        {
          title: t("teamTemplates.publicTemplates"),
          icon: "Globe2",
          id: "public-templates",
        },
        {
          title: t("teamTemplates.myTemplates"),
          icon: "UserRound",
          id: "my-templates",
        },
      ],
    },
  ];

  return (
    <BaseModal size="templates" open={open} setOpen={setOpen} className="p-0">
      <BaseModal.Content className="flex flex-col p-0">
        <div className="flex h-full">
          <SidebarProvider width="15rem" defaultOpen={false}>
            <Nav
              categories={categories}
              currentTab={currentTab}
              setCurrentTab={setCurrentTab}
            />
            <main className="flex flex-1 flex-col gap-4 overflow-auto p-6 md:gap-8">
              <TemplateContentComponent
                currentTab={currentTab}
                categories={categories.flatMap((category) => category.items)}
                enabled={open}
                loading={loading}
                onFlowCreating={handleFlowCreating}
              />
              <BaseModal.Footer>
                <div className="flex w-full flex-col justify-between gap-4 pb-4 sm:flex-row sm:items-center">
                  <div className="flex flex-col items-start justify-center">
                    <div className="font-semibold">
                      {t("templatesModal.startFromScratch")}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {t("templatesModal.startFromScratchDescription")}
                    </div>
                  </div>
                  <Button
                    onClick={handleCreateBlankFlow}
                    size="sm"
                    data-testid="blank-flow"
                    className={cn(
                      "shrink-0",
                      loading ? "cursor-default opacity-80" : "cursor-pointer",
                    )}
                  >
                    <ForwardedIconComponent
                      name="Plus"
                      className="h-4 w-4 shrink-0"
                    />
                    {t("templatesModal.blankFlow")}
                  </Button>
                </div>
              </BaseModal.Footer>
            </main>
          </SidebarProvider>
        </div>
      </BaseModal.Content>
    </BaseModal>
  );
}
