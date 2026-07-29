import type { useMutationFunctionType } from "@/types/api";
import type {
  TeamTemplate,
  UpdateTeamTemplatePayload,
} from "@/types/templates/types";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const usePatchTeamTemplate: useMutationFunctionType<
  undefined,
  UpdateTeamTemplatePayload,
  TeamTemplate
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();

  const patchTeamTemplate = async ({
    id,
    visibility,
  }: UpdateTeamTemplatePayload): Promise<TeamTemplate> => {
    const response = await api.patch<TeamTemplate>(
      `${getURL("TEAM_TEMPLATES")}/${id}`,
      { visibility },
    );
    return response.data;
  };

  return mutate(["usePatchTeamTemplate"], patchTeamTemplate, {
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["useGetTeamTemplates"] });
    },
    ...options,
  });
};
