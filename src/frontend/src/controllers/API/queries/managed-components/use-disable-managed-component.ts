import type { useMutationFunctionType } from "@/types/api";
import type { ManagedComponentBundle } from "@/types/managed-components";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const useDisableManagedComponent: useMutationFunctionType<
  undefined,
  string,
  ManagedComponentBundle
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();

  const disableManagedComponent = async (
    id: string,
  ): Promise<ManagedComponentBundle> => {
    const response = await api.post<ManagedComponentBundle>(
      `${getURL("MANAGED_COMPONENTS")}/${id}/disable`,
    );
    return response.data;
  };

  return mutate(["useDisableManagedComponent"], disableManagedComponent, {
    onSettled: (_data, _error, id) => {
      queryClient.invalidateQueries({ queryKey: ["useGetManagedComponents"] });
      queryClient.invalidateQueries({
        queryKey: ["useGetManagedComponent", id],
      });
      queryClient.invalidateQueries({ queryKey: ["useGetTypes"] });
    },
    ...options,
  });
};
