import { createBrowserRouter, RouterProvider } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import RequireAuth from "./components/RequireAuth";
import DepartmentPage from "./pages/departments/DepartmentPage";
import ExpensesPage from "./pages/expenses/ExpensesPage";
import HomePage from "./pages/HomePage";
import LeavesPage from "./pages/leaves/LeavesPage";
import LoginPage from "./pages/LoginPage";
import NotificationsPage from "./pages/notifications/NotificationsPage";
import UserListPage from "./pages/users/UserListPage";

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <MainLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <HomePage /> },
      { path: "users", element: <UserListPage /> },
      { path: "departments", element: <DepartmentPage /> },
      { path: "leaves", element: <LeavesPage /> },
      { path: "expenses", element: <ExpensesPage /> },
      { path: "notifications", element: <NotificationsPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
