import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { useGlobalJobStream } from "@/hooks/useJobStream";
import { useSetupStatus } from "@/api/queries";
import { SetupWizard } from "@/pages/SetupWizard";
import { Dashboard } from "@/pages/Dashboard";
import { NewVideo } from "@/pages/NewVideo";
import { Approval } from "@/pages/Approval";
import { Library } from "@/pages/Library";
import { Analytics } from "@/pages/Analytics";
import { Settings } from "@/pages/Settings";

export default function App() {
  // One socket for the whole app; folds job events into the Query cache + cost chip.
  useGlobalJobStream();

  const location = useLocation();
  const setup = useSetupStatus();

  // §7A.1: the wizard is shown automatically until setup reports complete:true.
  // While the status query is loading (or the backend is down), don't hard-redirect —
  // let the app render so empty states show instead of a blank screen.
  const setupComplete = setup.data?.complete ?? true;
  const onSetupRoute = location.pathname.startsWith("/setup");

  if (!setup.isLoading && !setupComplete && !onSetupRoute) {
    return <Navigate to="/setup" replace />;
  }

  return (
    <Routes>
      <Route path="/setup" element={<SetupWizard />} />
      <Route
        path="/*"
        element={
          <Layout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/new" element={<NewVideo />} />
              <Route path="/jobs/:id" element={<NewVideo />} />
              <Route path="/approve/:id" element={<Approval />} />
              <Route path="/library" element={<Library />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        }
      />
    </Routes>
  );
}
