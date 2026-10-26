import { useState, useEffect, useCallback, type FormEvent } from 'react';
import './CoursesPage.css';

/* ===================== ИМПОРТЫ ИЗ ТВОИХ API ===================== */
// Убедись, что deleteCourse экспортируется из '../api/courses'
import { 
  coursesApi, 
  type CourseUI, 
  type GetCoursesParams, 
  mapCourseDtoToUI 
} from '../api/courses';
import apiClient from '../api/client';

/* ===================== ТИПЫ (UI-модели) ===================== */
type MaterialStatus = 'done' | 'progress' | 'error';
type MaterialKind = 'PDF' | 'Текст' | 'Ссылка' | 'Документ';

interface MaterialItem {
  id: string;
  name: string;
  kind: MaterialKind;
  status: MaterialStatus;
  selected: boolean;
}

interface TestItem {
  id: string;
  name: string;
  date: string;
  questions: number;
  grade: number;
}

// Интерфейсы для API материалов (по Swagger)
interface MaterialResponse {
  materialId: string;
  courseId: string;
  title: string;
  typeMaterial: string;
  statusMaterial: string;
  sourceUri: string;
  fileType: string;
  materialSize: number;
  createdAt: string;
}

interface MaterialPage {
  content: MaterialResponse[];
  totalElements: number;
  totalPages: number;
  number: number;
  size: number;
  first: boolean;
  last: boolean;
  empty: boolean;
}

type SortOption = 'newest' | 'progress';

/* ===================== API МАТЕРИАЛОВ (inline, по Swagger) ===================== */
const materialsApi = {
  getByCourse: async (courseId: string, page = 0, size = 50): Promise<MaterialPage> => {
    // ИСПРАВЛЕНО: Передаем параметры плоско, как ждет Spring Data Pageable
    const params = new URLSearchParams();
    params.set('courseId', courseId);
    params.set('page', String(page));
    params.set('size', String(size));
    params.set('sort', 'createdAt,desc');
    
    const res = await apiClient.get<MaterialPage>('/api/materials', { params });
    return res.data;
  },
  upload: async (courseId: string, file: File): Promise<MaterialResponse> => {
    const form = new FormData();
    form.append('file', file);
    const res = await apiClient.post<MaterialResponse>(
      `/api/materials/upload?courseId=${courseId}`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return res.data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/materials/${id}`);
  },
};

/* ===================== МАППЕРЫ ===================== */
const mapMaterialToUI = (api: MaterialResponse): MaterialItem => {
  const kindMap: Record<string, MaterialKind> = {
    PDF: 'PDF', TEXT: 'Текст', LINK: 'Ссылка', DOCUMENT: 'Документ', DOCX: 'Документ',
  };
  const statusMap: Record<string, MaterialStatus> = {
    DONE: 'done', PROCESSING: 'progress', ERROR: 'error', QUEUED: 'progress',
  };
  return {
    id: api.materialId,
    name: api.title,
    kind: kindMap[api.typeMaterial?.toUpperCase()] ?? 'Документ',
    status: statusMap[api.statusMaterial?.toUpperCase()] ?? 'progress',
    selected: false,
  };
};

/* ===================== МОДАЛКА «СОЗДАНИЕ КУРСА» ===================== */
interface CreateCourseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: { name: string; description: string }) => Promise<void>;
}

const CreateCourseModal = ({ isOpen, onClose, onCreate }: CreateCourseModalProps) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = prevOverflow; document.removeEventListener('keydown', onKey); };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) { setName(''); setDescription(''); setError(''); }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) { setError('Введите название курса'); return; }
    setLoading(true);
    setError('');
    try {
      await onCreate({ name: trimmed, description: description.trim() });
      onClose();
    } catch (err: any) {
      setError(err.message || 'Ошибка при создании курса');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay is-open" role="dialog" aria-modal="true" aria-labelledby="modal-title"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть" disabled={loading}>×</button>
        <h2 className="modal-title" id="modal-title">Название курса</h2>
        <form onSubmit={handleSubmit} noValidate>
          <div className="modal-field">
            <label className="modal-label" htmlFor="cc-name">Название</label>
            <input id="cc-name" className="modal-input" type="text" placeholder="Например: Базы данных"
              value={name} onChange={(e) => { setName(e.target.value); if (error) setError(''); }} autoFocus disabled={loading} />
            {error && <span className="modal-error">{error}</span>}
          </div>
          <div className="modal-field">
            <label className="modal-label" htmlFor="cc-desc">Описание</label>
            <textarea id="cc-desc" className="modal-textarea" placeholder="Кратко опишите, чему посвящён курс"
              value={description} onChange={(e) => setDescription(e.target.value)} disabled={loading} />
          </div>
          <div className="modal-actions">
            <button className="modal-btn modal-btn-cancel" type="button" onClick={onClose} disabled={loading}>Отмена</button>
            <button className="modal-btn modal-btn-create" type="submit" disabled={loading}>
              {loading ? 'Создание…' : 'Создать курс'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};


/* ===================== СТРАНИЦА КУРСА (МАТЕРИАЛЫ + ТЕСТЫ) ===================== */
interface CourseViewProps {
  course: CourseUI;
  onBack: () => void;
}

const CourseView = ({ course, onBack }: CourseViewProps) => {
  const [materials, setMaterials] = useState<MaterialItem[]>([]);
  const [loadingMat, setLoadingMat] = useState(true);
  const [tests] = useState<TestItem[]>([]);

  // Загрузка материалов при монтировании/смене курса
  const fetchMaterials = useCallback(async () => {
    setLoadingMat(true);
    try {
      const data = await materialsApi.getByCourse(course.id);
      setMaterials(data.content.map(mapMaterialToUI));
    } catch (err) {
      console.error('Failed to load materials', err);
    } finally {
      setLoadingMat(false);
    }
  }, [course.id]);

  useEffect(() => { fetchMaterials(); }, [fetchMaterials]);

  return (
    <div className="course-page">
      <div className="course-columns">
        
        {/* ЛЕВАЯ КОЛОНКА: МАТЕРИАЛЫ */}
        <section className="tabbed-section">
          {/* Заголовок теперь СНАРУЖИ белого блока */}
          <h2 className="panel-title tab-header">Материалы ({materials.length})</h2>
          
          {/* Белый блок без верхней границы */}
          <div className="course-panel tabbed-panel">
            <button 
              className="btn-open-black" 
              type="button"
              onClick={() => window.location.href = `/courses/${course.id}/materials`}
            >
              Открыть материалы
            </button>

            <div className="materials-list">
              {loadingMat ? (
                <div className="skeleton-loader">Загрузка материалов…</div>
              ) : materials.length === 0 ? (
                <div className="empty-state">Пока нет материалов.</div>
              ) : (
                materials.map((m) => (
                  <div key={m.id} className="material-row">
                    <div className="material-body">
                      <p className="material-name">{m.name}</p>
                      <span className="material-type">{m.kind}</span>
                    </div>
                    <span className={`badge ${m.status}`}>
                      {m.status === 'done' && 'Обработан'}
                      {m.status === 'progress' && 'В процессе'}
                      {m.status === 'error' && 'Ошибка'}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        {/* ПРАВАЯ КОЛОНКА: ТЕСТЫ */}
        <section className="tabbed-section">
          <h2 className="panel-title tab-header">Тесты курса</h2>
          
          <div className="course-panel tabbed-panel">
            <button 
              className="btn-open-black" 
              type="button"
              onClick={() => window.location.href = '/results'}
            >
              Открыть тесты
            </button>

            <div className="tests-list">
              {tests.length === 0 ? (
                <div className="empty-state">Пока нет созданных тестов</div>
              ) : (
                tests.map((t) => (
                  <div key={t.id} className="test-row">
                    <div className="test-body">
                      <p className="test-name">{t.name}</p>
                      <span className="test-meta">{t.date} · {t.questions} вопросов</span>
                    </div>
                    <div className="test-grade" title="Оценка">{t.grade}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      </div>
      
      <button className="btn-back" type="button" onClick={onBack}>← Ко всем курсам</button>
    </div>
  );
};

/* ===================== ГЛАВНЫЙ КОМПОНЕНТ ===================== */
const CoursesPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('newest');
  const [currentPage, setCurrentPage] = useState(0);
  const [pageSize] = useState(10);

  const [courses, setCourses] = useState<CourseUI[]>([]);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [openedCourse, setOpenedCourse] = useState<CourseUI | null>(null);

  // ---- FETCH COURSES ----
  const fetchCourses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // ИСПРАВЛЕНО: Передаем параметры плоско, как требует твой бэкенд
      const params: GetCoursesParams = {
        title: searchQuery || undefined,
        page: currentPage,
        size: pageSize,
        sort: sortBy === 'newest' ? 'createdAt,desc' : 'title,asc',
      };
      
      const pageResponse = await coursesApi.getAll(params);
      const uiCourses = pageResponse.content.map((dto) => mapCourseDtoToUI(dto));
      
      setCourses(uiCourses);
      setTotalPages(pageResponse.totalPages);
    } catch (err: any) {
      console.error('Failed to load courses', err);
      setError(err.response?.data?.message || 'Не удалось загрузить курсы');
      setCourses([]);
      setTotalPages(0);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, currentPage, sortBy, pageSize]);

  useEffect(() => { fetchCourses(); }, [fetchCourses]);

  // ---- HANDLERS ----
  const handleCreateCourse = async (data: { name: string; description: string }) => {
    try {
      await coursesApi.create({ title: data.name, courseDescription: data.description });
      await fetchCourses(); // Перезагружаем список, чтобы получить реальный UUID
    } catch (err: any) {
      console.error('Ошибка создания курса:', err);
      throw new Error(err.response?.data?.message || 'Не удалось создать курс');
    }
  };

  const handleDeleteCourse = async (courseId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('Удалить курс безвозвратно?')) return;
    try {
      // Убедись, что в src/api/courses.ts есть export const deleteCourse
      await coursesApi.delete(courseId); 
      setCourses((prev) => prev.filter((c) => c.id !== courseId));
      if (courses.length === 1 && currentPage > 0) {
        setCurrentPage((p) => p - 1);
      } else {
        setTotalPages((prev) => Math.max(0, prev - 1));
      }
    } catch (err: any) {
      console.error('Delete course failed', err);
      alert(err.response?.data?.message || 'Не удалось удалить курс');
    }
  };

  const handleOpenCourse = (course: CourseUI) => setOpenedCourse(course);
  const handleBack = () => setOpenedCourse(null);

  // ---- RENDER ----
  if (openedCourse) {
    return <CourseView course={openedCourse} onBack={handleBack} />;
  }

  return (
    <div className="courses-page">
      <header className="courses-header">
        <div className="controls-bar">
          <input type="text" placeholder="Поиск по курсам..." value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(0); }} className="search-input" />
          <select value={sortBy} onChange={(e) => { setSortBy(e.target.value as SortOption); setCurrentPage(0); }} className="sort-select">
            <option value="newest">Сначала новые</option>
            <option value="progress">По прогрессу</option>
          </select>
          <button className="btn-create-course" onClick={() => setIsModalOpen(true)}>+ Создать курс</button>
        </div>
      </header>

      <main className="courses-grid">
        {loading ? (
          <div className="skeleton-loader">Загрузка курсов…</div>
        ) : error ? (
          <div className="empty-state" style={{ color: '#e64646' }}>
            <p>{error}</p>
            <button onClick={fetchCourses} className="btn-create-course" style={{ marginTop: '10px' }}>Повторить</button>
          </div>
        ) : courses.length === 0 ? (
          <div className="empty-state">Курсы не найдены. Создайте свой первый курс!</div>
        ) : (
          <>
            {courses.map((course) => (
              <article key={course.id} className="course-card">
                <div className="card-header">
                  <h3 className="card-title">{course.title}</h3>
                  <span className="card-badge">{course.testsCount}</span>
                </div>
                <p className="card-description">{course.description || 'Нет описания'}</p>
                <ul className="card-stats-list">
                  <li>• {course.materialsCount} материалов</li>
                  <li>• {course.testsCount} тестов</li>
                </ul>
                <div className="progress-section">
                  <div className="progress-label"><span>Готовность к сессии - {course.progress}%</span></div>
                  <div className="progress-bar-bg"><div className="progress-bar-fill" style={{ width: `${course.progress}%` }} /></div>
                </div>
                <div className="card-actions">
                  <button className="btn-open" type="button" onClick={() => handleOpenCourse(course)}>Открыть</button>
                  <button className="btn-delete" type="button" onClick={(e) => handleDeleteCourse(course.id, e)} title="Удалить курс">Удалить</button>
                </div>
              </article>
            ))}

            {/* ПАГИНАЦИЯ */}
            {totalPages > 1 && (
              <nav className="pagination" aria-label="Страницы курсов">
                <button className="page-btn" onClick={() => setCurrentPage(0)} disabled={currentPage === 0}>««</button>
                <button className="page-btn" onClick={() => setCurrentPage((p) => p - 1)} disabled={currentPage === 0}>«</button>
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 5) pageNum = i;
                  else if (currentPage <= 2) pageNum = i;
                  else if (currentPage >= totalPages - 3) pageNum = totalPages - 5 + i;
                  else pageNum = currentPage - 2 + i;
                  return (
                    <button key={pageNum} className={`page-btn ${pageNum === currentPage ? 'active' : ''}`}
                      onClick={() => setCurrentPage(pageNum)}>{pageNum + 1}</button>
                  );
                })}
                <button className="page-btn" onClick={() => setCurrentPage((p) => p + 1)} disabled={currentPage >= totalPages - 1}>»</button>
                <button className="page-btn" onClick={() => setCurrentPage(totalPages - 1)} disabled={currentPage >= totalPages - 1}>»»</button>
              </nav>
            )}
          </>
        )}
      </main>

      <CreateCourseModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onCreate={handleCreateCourse} />
    </div>
  );
};

export default CoursesPage;