import type { useQueryFunctionType } from "@/types/api";
import type { ManagedComponentDetail } from "@/types/managed-components";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const useGetManagedComponent: useQueryFunctionType<
  { id: string },
  ManagedComponentDetail
> = (params, options?) => {
  const { query } = UseRequestProcessor();

  const getManagedComponent = async (): Promise<ManagedComponentDetail> => {
    const response = await api.get<ManagedComponentDetail>(
      `${getURL("MANAGED_COMPONENTS")}/${params.id}`,
    );
    return response.data;
  };

  return query(["useGetManagedComponent", params.id], getManagedComponent, {
    enabled: !!params.id && (options?.enabled ?? true),
    ...options,
  });
};
