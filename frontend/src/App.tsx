import { createBrowserRouter, RouterProvider } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import RequireAuth from "./components/RequireAuth";
import DepartmentPage from "./pages/departments/DepartmentPage";
import HomePage from "./pages/HomePage";
import LeavesPage from "./pages/leaves/LeavesPage";
import LoginPage from "./pages/LoginPage";
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
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
