import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { Skill } from "./types";

export const usePostSkill: useMutationFunctionType<undefined, File> = (
  options?,
) => {
  const { mutate, queryClient } = UseRequestProcessor();

  const uploadSkill = async (file: File): Promise<Skill> => {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await api.post<Skill>(`${getURL("SKILLS")}/`, formData);
    return data;
  };

  return mutate(["usePostSkill"], uploadSkill, {
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["useGetSkills"] });
    },
    ...options,
  });
};
