import axios from "axios";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useDisableManagedComponent,
  useGetManagedComponent,
  useGetManagedComponents,
  usePostManagedComponent,
} from "@/controllers/API/queries/managed-components";
import useAlertStore from "@/stores/alertStore";
import { cn } from "@/utils/utils";

const MAX_COMPONENT_SIZE = 25 * 1024 * 1024;

function fieldLabel(field: Record<string, unknown>) {
  return String(field.display_name ?? field.name ?? "Unnamed");
}

function fieldType(field: Record<string, unknown>) {
  const type = field._input_type ?? field.type ?? field.types;
  return Array.isArray(type) ? type.join(", ") : String(type ?? "");
}

function fieldInfo(field: Record<string, unknown>) {
  return String(field.info ?? field.description ?? "");
}

function fieldDefault(field: Record<string, unknown>) {
  const type = fieldType(field).toLowerCase();
  const name = String(field.name ?? "").toLowerCase();
  if (
    type.includes("secret") ||
    type.includes("password") ||
    name.includes("api_key") ||
    name.includes("password") ||
    name.includes("token")
  ) {
    return "";
  }

  const value = field.value;
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export default function ComponentsPage() {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [selectedComponentId, setSelectedComponentId] = useState("");
  const { data: bundles, isLoading } = useGetManagedComponents();
  const selectedBundle = bundles?.find((bundle) => bundle.id === selectedId);
  const isManagedBundle = selectedBundle?.origin === "MANAGED";
  const { data: detail, isLoading: isDetailLoading } = useGetManagedComponent(
    { id: selectedId },
    { enabled: Boolean(selectedId) && isManagedBundle },
  );
  const displayedBundle = isManagedBundle ? detail : selectedBundle;
  const selectedComponent =
    displayedBundle?.components.find(
      (component) => component.namespaced_id === selectedComponentId,
    ) ?? displayedBundle?.components[0];
  const { mutate: uploadBundle, isPending: isUploading } =
    usePostManagedComponent();
  const { mutate: disableBundle, isPending: isDisabling } =
    useDisableManagedComponent();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);

  useEffect(() => {
    setSelectedComponentId(displayedBundle?.components[0]?.namespaced_id ?? "");
  }, [displayedBundle?.id]);

  const showError = (title: string, error: unknown) => {
    const message =
      (axios.isAxiosError(error) && error.response?.data?.detail) ||
      (error instanceof Error && error.message) ||
      t("errors.generic");
    setErrorData({ title, list: [String(message)] });
  };

  const handleFile = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      showError(
        t("settings.components.uploadFailed"),
        t("settings.components.zipOnly"),
      );
      return;
    }
    if (file.size > MAX_COMPONENT_SIZE) {
      showError(
        t("settings.components.uploadFailed"),
        t("settings.components.tooLarge"),
      );
      return;
    }
    uploadBundle(file, {
      onSuccess: (bundle) => {
        setSelectedId(bundle.id);
        setSuccessData({
          title: t("settings.components.uploadSuccess", {
            name: bundle.bundle_name,
          }),
        });
        if (inputRef.current) inputRef.current.value = "";
      },
      onError: (error) =>
        showError(t("settings.components.uploadFailed"), error),
    });
  };

  const handleDisable = () => {
    if (!detail || !window.confirm(t("settings.components.disableConfirm")))
      return;
    disableBundle(detail.id, {
      onSuccess: () =>
        setSuccessData({ title: t("settings.components.disableSuccess") }),
      onError: (error) =>
        showError(t("settings.components.disableFailed"), error),
    });
  };

  return (
    <div className="flex h-full w-full flex-col gap-6 overflow-auto pb-8">
      <div className="flex flex-col">
        <h2 className="flex items-center text-lg font-semibold tracking-tight">
          {t("settings.components.title")}
          <ForwardedIconComponent
            name="Blocks"
            className="ml-2 h-5 w-5 text-primary"
          />
        </h2>
        <p className="text-sm text-muted-foreground">
          {t("settings.components.description")}
        </p>
      </div>

      <section>
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          onChange={(event) => handleFile(event.target.files?.[0])}
          data-testid="managed-component-file-input"
        />
        <button
          type="button"
          disabled={isUploading}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragging(false);
            handleFile(event.dataTransfer.files[0]);
          }}
          className={cn(
            "flex min-h-36 w-full flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 px-6 py-6 text-center transition-colors",
            "hover:border-primary/60 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            isDragging && "border-primary bg-accent/60",
            isUploading && "cursor-wait opacity-60",
          )}
        >
          {isUploading ? (
            <Loading />
          ) : (
            <ForwardedIconComponent
              name="FileArchive"
              className="mb-2 h-8 w-8 text-muted-foreground"
            />
          )}
          <span className="text-sm font-medium">
            {t("settings.components.dropZip")}
          </span>
          <span className="mt-1 text-xs text-muted-foreground">
            {t("settings.components.requirements")}
          </span>
        </button>
      </section>

      <div className="grid min-h-0 grid-cols-1 gap-6 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.8fr)]">
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">
            {t("settings.components.installed")}
          </h3>
          {isLoading ? (
            <div className="flex min-h-32 items-center justify-center">
              <Loading />
            </div>
          ) : bundles?.length ? (
            bundles.map((bundle) => (
              <button
                key={bundle.id}
                type="button"
                onClick={() => setSelectedId(bundle.id)}
                className={cn(
                  "flex items-center justify-between rounded-lg border px-4 py-3 text-left hover:bg-accent",
                  selectedId === bundle.id && "border-primary bg-accent/50",
                )}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="truncate text-sm font-medium">
                      {bundle.bundle_name}
                    </div>
                    <Badge variant="outline" className="shrink-0">
                      {t(
                        bundle.origin === "SYSTEM"
                          ? "settings.components.system"
                          : "settings.components.uploaded",
                      )}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    v{bundle.version} · {bundle.components.length}{" "}
                    {t("settings.components.componentCount")}
                  </div>
                </div>
                <Badge
                  variant={bundle.status === "ACTIVE" ? "secondary" : "outline"}
                >
                  {t(
                    bundle.status === "ACTIVE"
                      ? "settings.components.active"
                      : bundle.status === "DISABLED"
                        ? "settings.components.disabled"
                        : "settings.components.error",
                  )}
                </Badge>
              </button>
            ))
          ) : (
            <div className="rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground">
              {t("settings.components.empty")}
            </div>
          )}
        </section>

        <section className="min-w-0">
          {!selectedId ? (
            <div className="flex min-h-64 items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
              {t("settings.components.selectOne")}
            </div>
          ) : (isManagedBundle && isDetailLoading) || !displayedBundle ? (
            <div className="flex min-h-64 items-center justify-center">
              <Loading />
            </div>
          ) : (
            <div className="flex flex-col gap-5 rounded-lg border p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-base font-semibold">
                    {displayedBundle.bundle_name}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {displayedBundle.description ||
                      t("settings.components.noDescription")}
                  </p>
                </div>
                {displayedBundle.can_disable &&
                  displayedBundle.status === "ACTIVE" && (
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={isDisabling}
                      onClick={handleDisable}
                    >
                      <ForwardedIconComponent
                        name="ArchiveX"
                        className="h-4 w-4"
                      />
                      {t("settings.components.disable")}
                    </Button>
                  )}
              </div>

              {detail && (
                <div className="rounded-md bg-muted/40 px-3 py-2 text-sm">
                  {t("settings.components.usedBy", {
                    count: detail.usage_count,
                  })}
                  {detail.usages.length > 0 && (
                    <ul className="mt-2 list-inside list-disc text-muted-foreground">
                      {detail.usages.map((usage) => (
                        <li key={usage.id}>
                          {usage.name} ({usage.node_count})
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {displayedBundle.components.length > 0 && (
                <div className="flex flex-col gap-2">
                  <label
                    htmlFor="managed-component-selector"
                    className="text-sm font-medium"
                  >
                    {t("settings.components.selectComponent")}
                  </label>
                  <Select
                    value={selectedComponent?.namespaced_id ?? ""}
                    onValueChange={setSelectedComponentId}
                  >
                    <SelectTrigger
                      id="managed-component-selector"
                      className="w-full"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {displayedBundle.components.map((component) => (
                        <SelectItem
                          key={component.namespaced_id}
                          value={component.namespaced_id}
                        >
                          {component.display_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {selectedComponent && (
                <div className="flex flex-col gap-3 rounded-lg border p-4">
                  <div>
                    <div className="font-medium">
                      {selectedComponent.display_name}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {selectedComponent.description}
                    </p>
                    {selectedComponent.documentation && (
                      <a
                        href={selectedComponent.documentation}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-primary underline-offset-4 hover:underline"
                      >
                        {t("settings.components.documentation")}
                      </a>
                    )}
                  </div>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    {[
                      {
                        title: t("settings.components.inputs"),
                        fields: selectedComponent.inputs,
                        isInput: true,
                      },
                      {
                        title: t("settings.components.outputs"),
                        fields: selectedComponent.outputs,
                        isInput: false,
                      },
                    ].map(({ title, fields, isInput }) => (
                      <div key={title}>
                        <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                          {title}
                        </div>
                        {fields.length ? (
                          <ul className="space-y-1 text-sm">
                            {fields.map((field, index) => (
                              <li
                                key={`${fieldLabel(field)}-${index}`}
                                className="rounded-md bg-muted/40 px-3 py-2"
                              >
                                <div className="font-medium">
                                  {fieldLabel(field)}
                                </div>
                                {fieldInfo(field) && (
                                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                                    {fieldInfo(field)}
                                  </p>
                                )}
                                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                                  {fieldType(field) && (
                                    <span>
                                      {t("settings.components.fieldType")}:{" "}
                                      {fieldType(field)}
                                    </span>
                                  )}
                                  {isInput && (
                                    <span>
                                      {field.required
                                        ? t("settings.components.required")
                                        : t("settings.components.optional")}
                                    </span>
                                  )}
                                  {isInput && field.advanced === true && (
                                    <span>
                                      {t("settings.components.advanced")}
                                    </span>
                                  )}
                                  {isInput && fieldDefault(field) && (
                                    <span className="break-all">
                                      {t("settings.components.defaultValue")}:{" "}
                                      {fieldDefault(field)}
                                    </span>
                                  )}
                                </div>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-sm text-muted-foreground">
                            —
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detail?.source_code && (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    {t("settings.components.sourceCode")}
                  </summary>
                  <pre className="mt-2 max-h-96 overflow-auto rounded-lg bg-muted p-4 text-xs">
                    <code>{detail.source_code}</code>
                  </pre>
                </details>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
