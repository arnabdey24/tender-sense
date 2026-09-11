import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type Profile = components["schemas"]["ProfileRead"]
export type ProfileUpdate = components["schemas"]["ProfileUpdate"]
export type Completeness = components["schemas"]["CompletenessRead"]
export type Taxonomies = components["schemas"]["TaxonomiesRead"]
export type Service = components["schemas"]["ServiceRead"]
export type ServiceIn = components["schemas"]["ServiceIn"]
export type PastProject = components["schemas"]["PastProjectRead"]
export type PastProjectIn = components["schemas"]["PastProjectIn"]
export type Certification = components["schemas"]["CertificationRead"]
export type Sector = components["schemas"]["Sector"]

/**
 * Editing the profile re-scores the whole feed in the background, so anything
 * showing a grade has to be dropped from cache alongside the profile itself.
 */
function invalidateProfileAndMatches(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: qk.profile.all() })
  void queryClient.invalidateQueries({ queryKey: qk.matches.all() })
}

export function useProfile() {
  return useQuery<Profile, ApiError>({
    queryKey: qk.profile.current(),
    queryFn: () => unwrap(api.GET("/api/v1/profile")),
  })
}

export function useCompleteness() {
  return useQuery<Completeness, ApiError>({
    queryKey: qk.profile.completeness(),
    queryFn: () => unwrap(api.GET("/api/v1/profile/completeness")),
  })
}

export function useTaxonomies() {
  return useQuery<Taxonomies, ApiError>({
    queryKey: qk.profile.taxonomies(),
    // Fixed option lists; refetching them on every mount is pure noise.
    staleTime: Infinity,
    queryFn: () => unwrap(api.GET("/api/v1/taxonomies")),
  })
}

export function useUpdateProfile(): UseMutationResult<
  Profile,
  ApiError,
  ProfileUpdate
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) => unwrap(api.PUT("/api/v1/profile", { body })),
    onSuccess: () => {
      invalidateProfileAndMatches(queryClient)
      toast.add({
        type: "success",
        title: "Profile saved",
        description: "Your tenders are being re-scored in the background.",
      })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not save the profile",
        description: error.message,
      }),
  })
}

export function useAddService(): UseMutationResult<Service, ApiError, ServiceIn> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) => unwrap(api.POST("/api/v1/profile/services", { body })),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
    onError: (error) =>
      toast.add({ type: "error", title: "Could not add", description: error.message }),
  })
}

export function useDeleteService(): UseMutationResult<void, ApiError, Service> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (service) =>
      unwrap(
        api.DELETE("/api/v1/profile/services/{service_id}", {
          params: { path: { service_id: service.id } },
        })
      ),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
  })
}

export function useAddProject(): UseMutationResult<
  PastProject,
  ApiError,
  PastProjectIn
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) => unwrap(api.POST("/api/v1/profile/projects", { body })),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
    onError: (error) =>
      toast.add({ type: "error", title: "Could not add", description: error.message }),
  })
}

export function useUpdateProject(): UseMutationResult<
  PastProject,
  ApiError,
  { id: string; body: PastProjectIn }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }) =>
      unwrap(
        api.PUT("/api/v1/profile/projects/{project_id}", {
          params: { path: { project_id: id } },
          body,
        })
      ),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
    onError: (error) =>
      toast.add({ type: "error", title: "Could not save", description: error.message }),
  })
}

export function useDeleteProject(): UseMutationResult<void, ApiError, PastProject> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (project) =>
      unwrap(
        api.DELETE("/api/v1/profile/projects/{project_id}", {
          params: { path: { project_id: project.id } },
        })
      ),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
  })
}

export function useAddCertification(): UseMutationResult<
  Certification,
  ApiError,
  { label: string }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) =>
      unwrap(api.POST("/api/v1/profile/certifications", { body })),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
    onError: (error) =>
      toast.add({ type: "error", title: "Could not add", description: error.message }),
  })
}

export function useDeleteCertification(): UseMutationResult<
  void,
  ApiError,
  Certification
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (certification) =>
      unwrap(
        api.DELETE("/api/v1/profile/certifications/{certification_id}", {
          params: { path: { certification_id: certification.id } },
        })
      ),
    onSuccess: () => invalidateProfileAndMatches(queryClient),
  })
}

export function useRematch(): UseMutationResult<unknown, ApiError, void> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/profile/rematch")),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.matches.all() })
      toast.add({
        type: "success",
        title: "Re-scoring started",
        description: "Grades will refresh in a moment.",
      })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not start re-scoring",
        description: error.message,
      }),
  })
}
