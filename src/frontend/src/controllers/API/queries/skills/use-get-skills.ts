import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { Skill } from "./types";

export const useGetSkills: useQueryFunctionType<undefined, Skill[]> = (
  options,
) => {
  const { query } = UseRequestProcessor();

  const getSkills = async (): Promise<Skill[]> => {
    const { data } = await api.get<Skill[]>(`${getURL("SKILLS")}/`);
    return data;
  };

  return query(["useGetSkills"], getSkills, {
    refetchOnWindowFocus: false,
    ...options,
  });
};
