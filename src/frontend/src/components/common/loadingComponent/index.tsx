import { useTranslation } from "react-i18next";
import type { LoadingComponentProps } from "../../../types/components";

export default function LoadingComponent({
  remSize,
}: LoadingComponentProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <>
      <style>
        {`
          .load-container {
            box-sizing: border-box;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100vw;
            min-height: 100vh;
          }
          .load-container h2 {
            position: relative;
            font-size: 80px;
            color: #79BBFF;
            -webkit-text-stroke: 1px #fff;
          }
          .load-container h2::before {
            content: 'AI Flow';
            position: absolute;
            top: 0;
            left: 0;
            width: 0;
            height: 100%;
            color: #409eff;
            -webkit-text-stroke: 0 #79BBFF;
            border-right: none;
            white-space: nowrap;
            overflow: hidden;
            animation: move-border 2s linear infinite;
          }
          @keyframes move-border {
            0%, 100% { width: 0; }
            70% { width: 100%; }
          }
        `}
      </style>

      <div
        role="status"
        className="load-container flex flex-col items-center justify-center"
      >
        <div>
          <h2>AI Flow</h2>
          <h3 style={{ color: '#409eff', textAlign: 'center', fontSize: '20px' }}>
            正在加载系统资源，请耐心等待...
          </h3>
        </div>
      </div>
    </>
  );
}