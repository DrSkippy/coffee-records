import { Route, Routes, Navigate } from "react-router-dom";
import AppLayout from "./components/layout/AppShell";
import ShotsPage from "./pages/ShotsPage";
import NewShotPage from "./pages/NewShotPage";
import CoffeesPage from "./pages/CoffeesPage";
import EquipmentPage from "./pages/EquipmentPage";
import ReportsPage from "./pages/ReportsPage";

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/shots" replace />} />
        <Route path="/shots" element={<ShotsPage />} />
        <Route path="/shots/new" element={<NewShotPage />} />
        <Route path="/coffees" element={<CoffeesPage />} />
        <Route path="/equipment" element={<EquipmentPage />} />
        <Route path="/reports" element={<ReportsPage />} />
      </Routes>
    </AppLayout>
  );
}
