import { useTranslation } from "react-i18next";
import type { useMutationFunctionType } from "@/types/api";
import type { FlowType } from "@/types/flow";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const useGetBasicExample: useMutationFunctionType<undefined, string> = (
  options,
) => {
  const { mutate } = UseRequestProcessor();
  const { i18n } = useTranslation();

  const getBasicExample = async (flowId: string): Promise<FlowType> => {
    const response = await api.get<FlowType>(
      `${getURL("FLOWS")}/basic_examples/${flowId}`,
    );
    return response.data;
  };

  return mutate(
    ["useGetBasicExample", i18n.language],
    getBasicExample,
    options,
  );
};
