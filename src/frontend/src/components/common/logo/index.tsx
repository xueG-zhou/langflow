import { forwardRef, type ImgHTMLAttributes } from "react";
import logoSrc from "@/assets/AIFlow-logo.png";

export type LogoProps = ImgHTMLAttributes<HTMLImageElement>;

export const Logo = forwardRef<HTMLImageElement, LogoProps>(
  ({ className, alt = "AIFlow", ...props }, ref) => (
    <img ref={ref} src={logoSrc} className={className} alt={alt} {...props} />
  ),
);
Logo.displayName = "Logo";

export default Logo;
