import apiClient from './client';

export interface Course {
  id: string;                    // UUID в Java → string в TS
  title: string;
  courseDescription: string;     // camelCase как в Java DTO
  ownerId: string;
  createdAt: string;             // ISO-строка LocalDateTime
  updatedAt: string;
}

// Структура ответа Spring Data Page<T>
export interface CoursePage {
  content: Course[];
  totalPages: number;
  totalElements: number;
  number: number;                // текущая страница (с 0)
  size: number;
  first: boolean;
  last: boolean;
  empty: boolean;
}

export interface CreateCourseRequest {
  title: string;
  courseDescription: string;
}

export interface UpdateCourseRequest {
  title?: string;
  courseDescription?: string;
}

export interface CourseFilter {
  title?: string;
  page?: number;                 // по умолчанию 0
  size?: number;                 // по умолчанию 20
  sort?: string;                 // например: "createdAt,desc" или "title,asc"
}

export const getCourses = async (params: CourseFilter): Promise<CoursePage> => {
  const response = await apiClient.get<CoursePage>('/api/courses', {
    params: {
      title: params.title || undefined,
      page: params.page ?? 0,
      size: params.size ?? 20,
      sort: params.sort || undefined,
    },
  });
  return response.data;
};

export const getCourseById = async (id: string): Promise<Course> => {
  const response = await apiClient.get<Course>(`/api/courses/${id}`);
  return response.data;
};

export const createCourse = async (data: CreateCourseRequest): Promise<Course> => {
  const response = await apiClient.post<Course>('/api/courses', data);
  return response.data;
};

export const updateCourse = async (
  id: string,
  data: UpdateCourseRequest
): Promise<Course> => {
  const response = await apiClient.put<Course>(`/api/courses/${id}`, data);
  return response.data;
};

export const deleteCourse = async (id: string): Promise<void> => {
  await apiClient.delete(`/api/courses/${id}`);
};

export const formatDate = (isoString: string): string => {
  if (!isoString) return '';
  return new Date(isoString).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

export const truncateText = (text: string, maxLength: number = 120): string => {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trim() + '…';
};