import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/AppLayout";
import { RequireAuth } from "@/components/RequireAuth";
import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { EstablishmentsPage } from "@/pages/EstablishmentsPage";
import { FindingsPage } from "@/pages/FindingsPage";
import { HomePage } from "@/pages/HomePage";
import { ProfilePage } from "@/pages/ProfilePage";
import { RulesPage } from "@/pages/RulesPage";
import { WorklistPage } from "@/pages/WorklistPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Never retry authentication or authorisation failures. The API client has
        // already attempted a token refresh, so a second 401 is genuine, and
        // retrying a 403 or 404 cannot change the answer.
        if (error instanceof ApiError) {
          if (error.isAuthError || error.isForbidden || error.isNotFound) {
            return false;
          }
        }
        return failureCount < 2;
      },
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route element={<AppLayout />}>
              {/* Open to visitors. The landing page and the rule packs are public
                  on purpose: an employer should be able to read the tests that
                  will be applied to them before they have an account. */}
              <Route index element={<HomePage />} />
              <Route path="rules" element={<RulesPage />} />
              <Route path="profile" element={<ProfilePage />} />

              {/* Documents renders its own signed-out prompt rather than
                  redirecting, so a visitor can see what the screen is for. */}
              <Route path="documents" element={<DocumentsPage />} />

              <Route
                path="establishments"
                element={
                  <RequireAuth>
                    <EstablishmentsPage />
                  </RequireAuth>
                }
              />
              <Route
                path="findings"
                element={
                  <RequireAuth>
                    <FindingsPage />
                  </RequireAuth>
                }
              />
              <Route
                path="worklist"
                element={
                  <RequireAuth roles={["INSPECTOR", "ADMIN", "ANALYST"]}>
                    <WorklistPage />
                  </RequireAuth>
                }
              />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
