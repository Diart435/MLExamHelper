// src/api/courses.ts
import apiClient from './client';

// ===== DTO (Wire Format — 1-в-1 как в PDF) =====
export interface CourseDto {
  courseId: string;
  title: string;
  courseDescription: string;
}

export interface CreateCourseRequest {
  title: string;
  courseDescription: string;
}

export interface UpdateCourseRequest {
  title?: string;
  courseDescription?: string;
}

// Spring Data Page ответ
export interface PageResponse<T> {
  content: T[];
  totalPages: number;
  totalElements: number;
  size: number;
  number: number;
  numberOfElements: number;
  first: boolean;
  last: boolean;
  empty: boolean;
}

export type CoursePage = PageResponse<CourseDto>;

// ===== Query Params (плоские, как в PDF) =====
export interface GetCoursesParams {
  title?: string;      // фильтр по названию
  page?: number;       // default 0
  size?: number;       // default 10 (PDF: default 10)
  sort?: string;       // e.g. "createdAt,desc"
}

// ===== API =====
const BASE = '/api/courses';

export const coursesApi = {
  /** GET /api/courses?title=...&page=0&size=10&sort=createdAt,desc */
  getAll: (params: GetCoursesParams = {}) => {
    const sp = new URLSearchParams();
    if (params.title) sp.set('title', params.title);
    sp.set('page', String(params.page ?? 0));
    sp.set('size', String(params.size ?? 10));
    if (params.sort) sp.set('sort', params.sort);
    return apiClient.get<CoursePage>(`${BASE}?${sp.toString()}`).then((r) => r.data);
  },

  /** GET /api/courses/{id} */
  getById: (id: string) => apiClient.get<CourseDto>(`${BASE}/${id}`).then((r) => r.data),

  /** POST /api/courses */
  create: (data: CreateCourseRequest) => apiClient.post<CourseDto>(BASE, data).then((r) => r.data),

  /** PUT /api/courses/{id} */
  update: (id: string, data: UpdateCourseRequest) => apiClient.put<CourseDto>(`${BASE}/${id}`, data).then((r) => r.data),

  /** DELETE /api/courses/{id} */
  delete: (id: string) => apiClient.delete(`${BASE}/${id}`),
};

// ===== UI Mappers =====
export interface CourseUI {
  id: string;
  title: string;
  description: string;
  materialsCount: number;
  testsCount: number;
  progress: number;
  createdAt: string;
}

export const mapCourseDtoToUI = (d: CourseDto, extra: Partial<CourseUI> = {}): CourseUI => ({
  id: d.courseId,
  title: d.title,
  description: d.courseDescription,
  materialsCount: 0,
  testsCount: 0,
  progress: 0,
  createdAt: new Date().toISOString(),
  ...extra,
});