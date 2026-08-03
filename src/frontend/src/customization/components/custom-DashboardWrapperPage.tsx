import { Outlet } from "react-router-dom";
import { ENABLE_CUSTOM_APP_HEADER } from "@/customization/feature-flags";
import useTheme from "@/customization/hooks/use-custom-theme";
import { DashboardWrapperPage } from "@/pages/DashboardWrapperPage";
import { CustomAppHeader } from "./custom-app-header";

export const CustomDashboardWrapperPage = () => {
  useTheme();
  if (ENABLE_CUSTOM_APP_HEADER) {
    return (
      <div className="flex h-screen w-full flex-col overflow-hidden">
        <CustomAppHeader />
        <div className="flex w-full flex-1 flex-row overflow-hidden">
          <Outlet />
        </div>
      </div>
    );
  }
  return <DashboardWrapperPage />;
};

export default CustomDashboardWrapperPage;
