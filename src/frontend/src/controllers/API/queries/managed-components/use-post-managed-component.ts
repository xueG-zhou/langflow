import type { useMutationFunctionType } from "@/types/api";
import type { ManagedComponentBundle } from "@/types/managed-components";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const usePostManagedComponent: useMutationFunctionType<
  undefined,
  File,
  ManagedComponentBundle
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();

  const uploadManagedComponent = async (
    file: File,
  ): Promise<ManagedComponentBundle> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await api.post<ManagedComponentBundle>(
      getURL("MANAGED_COMPONENTS"),
      formData,
    );
    return response.data;
  };

  return mutate(["usePostManagedComponent"], uploadManagedComponent, {
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["useGetManagedComponents"] });
      queryClient.invalidateQueries({ queryKey: ["useGetTypes"] });
    },
    ...options,
  });
};
