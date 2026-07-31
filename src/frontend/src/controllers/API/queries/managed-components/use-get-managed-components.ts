import type { useQueryFunctionType } from "@/types/api";
import type { ManagedComponentBundle } from "@/types/managed-components";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const useGetManagedComponents: useQueryFunctionType<
  undefined,
  ManagedComponentBundle[]
> = (options?) => {
  const { query } = UseRequestProcessor();

  const getManagedComponents = async (): Promise<ManagedComponentBundle[]> => {
    const response = await api.get<ManagedComponentBundle[]>(
      getURL("MANAGED_COMPONENTS"),
    );
    return response.data;
  };

  return query(["useGetManagedComponents"], getManagedComponents, {
    refetchOnWindowFocus: false,
    ...options,
  });
};
