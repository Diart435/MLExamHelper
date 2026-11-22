import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react';
import { useParams } from 'react-router-dom';
import apiClient from '../api/client';
import { coursesApi, type CourseDto } from '../api/courses';
import './MaterialsPage.css';

/* ===================== ТИПЫ ===================== */

type MaterialType = 'PDF' | 'DOCX';
type MaterialStatus = 'PROCESSING' | 'READY' | 'ERROR';
type TypeFilter = 'ALL' | MaterialType;
type StatusFilter = 'ALL' | MaterialStatus;
type SortMode = 'newest' | 'oldest' | 'title' | 'size';

interface MaterialResponse {
  materialId: string;
  courseId: string;
  title: string;
  typeMaterial: string;
  statusMaterial: string;
  sourceUri: string | null;
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

const PAGE_SIZE = 6;
const MAX_FILE_SIZE = 50 * 1024 * 1024;

/* ===================== API МАТЕРИАЛОВ ===================== */

const materialsApi = {
  getByCourse: async (courseId: string, page = 0, size = PAGE_SIZE): Promise<MaterialPage> => {
    const params = new URLSearchParams();
    params.set('courseId', courseId);
    params.set('page', String(page));
    params.set('size', String(size));
    params.set('sort', 'createdAt,desc');

    const res = await apiClient.get<MaterialPage>('/materials', { params });
    return res.data;
  },
  getById: async (id: string): Promise<MaterialResponse> => {
    const res = await apiClient.get<MaterialResponse>(`/materials/${id}`);
    return res.data;
  },
  upload: async (courseId: string, file: File): Promise<MaterialResponse> => {
    const form = new FormData();
    form.append('file', file);
    const res = await apiClient.post<MaterialResponse>(
      `/materials/upload?courseId=${courseId}`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return res.data;
  },
  remove: async (id: string): Promise<void> => {
    await apiClient.delete(`/materials/${id}`);
  },
  rename: async (id: string, title: string): Promise<MaterialResponse> => {
    const res = await apiClient.put<MaterialResponse>(`/materials/change/${id}`, { title });
    return res.data;
  },
};

/* ===================== ХЕЛПЕРЫ ===================== */

const STATUS_META: Record<MaterialStatus, { label: string; className: string }> = {
  READY: { label: 'Обработан', className: 'is-ready' },
  PROCESSING: { label: 'В процессе', className: 'is-processing' },
  ERROR: { label: 'Ошибка', className: 'is-error' },
};

const normalizeStatus = (status: string): MaterialStatus => {
  if (status === 'READY' || status === 'ERROR') return status;
  return 'PROCESSING';
};

const formatSize = (bytes: number): string => {
  if (!bytes || bytes < 0) return '—';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = value >= 10 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
};

const formatDate = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const getErrorMessage = (err: unknown, fallback: string): string => {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const response = (err as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) return response.data.message;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
};

/* ===================== ИКОНКИ ===================== */

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
    <path d="M16 16l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M4 15.5v2A2.5 2.5 0 006.5 20h11a2.5 2.5 0 002.5-2.5v-2"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
    />
  </svg>
);

const DocIcon = () => (
  <svg viewBox="0 0 36 44" fill="none" aria-hidden="true">
    <path
      d="M7 3.5h14.5L30 12v27a2 2 0 01-2 2H7a2 2 0 01-2-2v-33a2 2 0 012-2z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
    />
    <path d="M21.5 3.5V12H30" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <path d="M10.5 20h14M10.5 26h14M10.5 32h9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const TrashIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M4 7h16M9 7V4.5h6V7m-9 0l1 13h10l1-13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M10 11v5.5M14 11v5.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
  </svg>
);

const PencilIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M4 20l4.5-1 10-10a2.12 2.12 0 00-3-3l-10 10L4 20z"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinejoin="round"
    />
  </svg>
);

const EmptyIcon = () => (
  <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <path
      d="M14 10h24l12 12v32a4 4 0 01-4 4H14a4 4 0 01-4-4V14a4 4 0 014-4z"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinejoin="round"
    />
    <path d="M38 10v12h12" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M20 34h20M20 42h20M20 50h12" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

/* ===================== СТРАНИЦА ===================== */

const MaterialsPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const isCourseMode = Boolean(courseId);

  const [selectedCourseId, setSelectedCourseId] = useState('');
  const [courseOptions, setCourseOptions] = useState<CourseDto[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursePickerOpen, setCoursePickerOpen] = useState(false);

  const effectiveCourseId = courseId ?? selectedCourseId;

  const [materials, setMaterials] = useState<MaterialResponse[]>([]);
  const [totalElements, setTotalElements] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('ALL');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [sortMode, setSortMode] = useState<SortMode>('newest');

  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const coursePickerRef = useRef<HTMLDivElement>(null);

  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  /* ---------- выбор курса (общий режим /materials) ---------- */

  useEffect(() => {
    if (isCourseMode) return;
    let cancelled = false;
    setCoursesLoading(true);
    coursesApi
      .getAll({ size: 100 })
      .then((data) => {
        if (cancelled) return;
        setCourseOptions(data.content ?? []);
      })
      .catch(() => {
        if (cancelled) return;
        setCourseOptions([]);
      })
      .finally(() => {
        if (!cancelled) setCoursesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isCourseMode]);

  const selectedCourse = useMemo(
    () => courseOptions.find((course) => course.courseId === selectedCourseId) ?? null,
    [courseOptions, selectedCourseId],
  );

  useEffect(() => {
    if (!coursePickerOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!coursePickerRef.current?.contains(event.target as Node)) {
        setCoursePickerOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [coursePickerOpen]);

  useEffect(() => {
    setPage(0);
    setSelected(new Set());
    setPendingFiles([]);
    setUploadError(null);
    setUploadNotice(null);
    setListError(null);
    setCoursePickerOpen(false);
  }, [effectiveCourseId]);

  /* ---------- загрузка данных ---------- */

  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback((silent = false) => {
    if (!silent) setLoading(true);
    setListError(null);
    setReloadKey((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!effectiveCourseId) {
      setMaterials([]);
      setTotalElements(0);
      setTotalPages(0);
      setListError(null);
      setLoading(false);
      setSelected(new Set());
      return;
    }

    let cancelled = false;
    setLoading(true);

    const fetchPage = async () => {
      try {
        const data = await materialsApi.getByCourse(effectiveCourseId, page, PAGE_SIZE);
        if (cancelled) return;

        setMaterials(data.content);
        setTotalElements(data.totalElements);
        setTotalPages(data.totalPages);
        setListError(null);

        // Убираем из выбранных материалы, которых больше нет в списке
        setSelected((prev) => {
          const ids = new Set(data.content.map((material) => material.materialId));
          const next = new Set([...prev].filter((id) => ids.has(id)));
          return next.size === prev.size ? prev : next;
        });
      } catch (err) {
        if (cancelled) return;
        setListError(getErrorMessage(err, 'Не удалось загрузить материалы'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void fetchPage();
    return () => {
      cancelled = true;
    };
  }, [effectiveCourseId, page, reloadKey]);

  // Пока есть материалы в обработке — тихо обновляем список
  const hasProcessing = materials.some(
    (material) => normalizeStatus(material.statusMaterial) === 'PROCESSING',
  );

  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setInterval(() => {
      reload(true);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [hasProcessing, reload]);

  /* ---------- фильтрация и сортировка ---------- */

  const visibleMaterials = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = materials.filter((material) => {
      if (normalizedQuery && !material.title.toLowerCase().includes(normalizedQuery)) return false;
      if (typeFilter !== 'ALL' && material.typeMaterial !== typeFilter) return false;
      if (statusFilter !== 'ALL' && normalizeStatus(material.statusMaterial) !== statusFilter) {
        return false;
      }
      return true;
    });

    return filtered.sort((a, b) => {
      switch (sortMode) {
        case 'oldest':
          return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
        case 'title':
          return a.title.localeCompare(b.title, 'ru');
        case 'size':
          return b.materialSize - a.materialSize;
        default:
          return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      }
    });
  }, [materials, query, typeFilter, statusFilter, sortMode]);

  const filtersActive =
    query.trim() !== '' || typeFilter !== 'ALL' || statusFilter !== 'ALL' || sortMode !== 'newest';

  const allVisibleSelected =
    visibleMaterials.length > 0 &&
    visibleMaterials.every((material) => selected.has(material.materialId));

  /* ---------- выбор ---------- */

  const toggleSelectAll = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleMaterials.forEach((material) => next.delete(material.materialId));
      } else {
        visibleMaterials.forEach((material) => next.add(material.materialId));
      }
      return next;
    });
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /* ---------- загрузка файлов ---------- */

  const onPickClick = () => {
    if (uploading || !effectiveCourseId) return;
    fileInputRef.current?.click();
  };

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (!incoming.length) return;

    const accepted: File[] = [];
    const problems: string[] = [];

    incoming.forEach((file) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
      if (extension !== 'pdf' && extension !== 'docx') {
        problems.push(`${file.name} — только PDF или DOCX`);
      } else if (file.size === 0) {
        problems.push(`${file.name} — пустой файл`);
      } else if (file.size > MAX_FILE_SIZE) {
        problems.push(`${file.name} — больше 50 МБ`);
      } else {
        accepted.push(file);
      }
    });

    if (accepted.length) {
      setPendingFiles((prev) => [...prev, ...accepted]);
      setUploadNotice(null);
    }
    setUploadError(problems.length ? problems.join('; ') : null);
  };

  const removePendingFile = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, itemIndex) => itemIndex !== index));
  };

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = '';
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!dragActive) setDragActive(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setDragActive(false);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    if (event.dataTransfer.files) addFiles(event.dataTransfer.files);
  };

  const handleUpload = async () => {
    if (!effectiveCourseId || !pendingFiles.length || uploading) return;

    setUploading(true);
    setUploadError(null);
    setUploadNotice(null);

    const files = pendingFiles;
    const failed: string[] = [];
    let uploaded = 0;

    for (const file of files) {
      try {
        await materialsApi.upload(effectiveCourseId, file);
        uploaded += 1;
      } catch (err) {
        failed.push(`${file.name}: ${getErrorMessage(err, 'ошибка загрузки')}`);
      }
    }

    setPendingFiles([]);
    setUploading(false);

    if (uploaded > 0) {
      setUploadNotice(
        `Загружено файлов: ${uploaded}. Обработка материала может занять несколько минут.`,
      );
    }
    if (failed.length) setUploadError(failed.join('; '));

    if (page === 0) reload(true);
    else {
      setLoading(true);
      setPage(0);
    }
  };

  /* ---------- действия с материалами ---------- */

  const handleOpen = async (material: MaterialResponse) => {
    setBusyId(material.materialId);
    try {
      const full = await materialsApi.getById(material.materialId);
      if (full.sourceUri) {
        window.open(full.sourceUri, '_blank', 'noopener,noreferrer');
      } else {
        setListError('Ссылка на файл недоступна. Попробуйте позже.');
      }
    } catch (err) {
      setListError(getErrorMessage(err, 'Не удалось открыть материал'));
    } finally {
      setBusyId(null);
    }
  };

  const handleRename = async (material: MaterialResponse) => {
    const nextTitle = window.prompt('Новое название материала', material.title);
    if (nextTitle === null) return;

    const trimmed = nextTitle.trim();
    if (!trimmed || trimmed === material.title) return;

    setBusyId(material.materialId);
    try {
      await materialsApi.rename(material.materialId, trimmed);
      reload(true);
    } catch (err) {
      setListError(getErrorMessage(err, 'Не удалось переименовать материал'));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (material: MaterialResponse) => {
    if (!window.confirm(`Удалить «${material.title}»?`)) return;

    setBusyId(material.materialId);
    try {
      await materialsApi.remove(material.materialId);
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(material.materialId);
        return next;
      });

      if (materials.length <= 1 && page > 0) {
        setLoading(true);
        setPage((prev) => prev - 1);
      } else {
        reload(true);
      }
    } catch (err) {
      setListError(getErrorMessage(err, 'Не удалось удалить материал'));
    } finally {
      setBusyId(null);
    }
  };

  const handleDeleteSelected = async () => {
    if (!selected.size || deleting) return;
    if (!window.confirm(`Удалить выбранные материалы (${selected.size})?`)) return;

    setDeleting(true);
    setListError(null);
    const ids = [...selected];

    const results = await Promise.allSettled(ids.map((id) => materialsApi.remove(id)));
    const failedCount = results.filter((result) => result.status === 'rejected').length;

    setSelected(new Set());
    setDeleting(false);

    if (failedCount > 0) {
      setListError(`Не удалось удалить материалов: ${failedCount} из ${ids.length}`);
    }

    if (page === 0) reload(true);
    else {
      setLoading(true);
      setPage(0);
    }
  };

  const resetFilters = () => {
    setQuery('');
    setTypeFilter('ALL');
    setStatusFilter('ALL');
    setSortMode('newest');
  };

  /* ---------- рендер ---------- */

  const hasCourse = Boolean(effectiveCourseId);

  return (
    <div className="materials-page">
      <div className="materials-page__pattern" aria-hidden="true" />

      <div className="materials-page__content">
        {/* ---------- ПАНЕЛЬ ЗАГРУЗКИ ---------- */}
        <section className="materials-block">
          <div className="materials-tab">Загрузка материала</div>

          <div className="materials-panel materials-panel--upload">
            <div
              className={`upload-zone${dragActive ? ' is-dragging' : ''}${!hasCourse ? ' is-disabled' : ''}`}
              onClick={hasCourse ? onPickClick : undefined}
              onDragEnter={hasCourse ? handleDragOver : undefined}
              onDragOver={hasCourse ? handleDragOver : undefined}
              onDragLeave={hasCourse ? handleDragLeave : undefined}
              onDrop={hasCourse ? handleDrop : undefined}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                multiple
                className="upload-zone__input"
                onChange={handleFileInput}
                tabIndex={-1}
                disabled={!hasCourse}
              />

              <span className="upload-zone__icon">
                <UploadIcon />
              </span>
              <h2 className="upload-zone__title">Загрузите материалы</h2>
              <p className="upload-zone__hint">
                {hasCourse
                  ? 'Перетащите файлы сюда или выберите на устройстве'
                  : 'Сначала выберите курс, чтобы загрузить материалы'}
              </p>
              <p className="upload-zone__formats">PDF или DOCX · до 50 МБ</p>

              {pendingFiles.length > 0 && (
                <ul className="upload-zone__files" onClick={(event) => event.stopPropagation()}>
                  {pendingFiles.map((file, index) => (
                    <li key={`${file.name}-${file.lastModified}-${index}`} className="upload-zone__file">
                      <span className="upload-zone__file-name" title={file.name}>
                        {file.name}
                      </span>
                      <span className="upload-zone__file-size">{formatSize(file.size)}</span>
                      <button
                        type="button"
                        className="upload-zone__file-remove"
                        onClick={() => removePendingFile(index)}
                        aria-label={`Убрать ${file.name}`}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="upload-zone__actions" onClick={(event) => event.stopPropagation()}>
                <button
                  type="button"
                  className="materials-btn materials-btn--outline"
                  onClick={onPickClick}
                  disabled={uploading || !hasCourse}
                >
                  Выберите файлы
                </button>
                {pendingFiles.length > 0 && (
                  <button
                    type="button"
                    className="materials-btn materials-btn--primary"
                    onClick={() => void handleUpload()}
                    disabled={uploading}
                  >
                    {uploading
                      ? 'Загрузка…'
                      : `Загрузить${pendingFiles.length > 1 ? ` (${pendingFiles.length})` : ''}`}
                  </button>
                )}
              </div>
            </div>

            {(uploadError || uploadNotice) && (
              <div
                className={`upload-message${uploadError ? ' is-error' : ' is-success'}`}
                role="status"
              >
                {uploadError ?? uploadNotice}
              </div>
            )}
          </div>
        </section>

        {/* ---------- ПАНЕЛЬ МАТЕРИАЛОВ ---------- */}
        <section className="materials-block">
          <div className="materials-tab">
            Материалы
            <span className="materials-tab__count">{totalElements}</span>
          </div>

          <div className="materials-panel materials-panel--list">
            <div className="materials-filters">
              <label className="materials-search">
                <span className="materials-search__icon">
                  <SearchIcon />
                </span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Поиск по названию"
                  aria-label="Поиск материалов по названию"
                />
                {query && (
                  <button
                    type="button"
                    className="materials-search__clear"
                    onClick={() => setQuery('')}
                    aria-label="Очистить поиск"
                  >
                    ×
                  </button>
                )}
              </label>

              <select
                className="materials-filter"
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value as TypeFilter)}
                aria-label="Фильтр по типу материала"
              >
                <option value="ALL">Все типы</option>
                <option value="PDF">PDF</option>
                <option value="DOCX">DOCX</option>
              </select>

              <select
                className="materials-filter"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                aria-label="Фильтр по статусу материала"
              >
                <option value="ALL">Все статусы</option>
                <option value="READY">Обработан</option>
                <option value="PROCESSING">В процессе</option>
                <option value="ERROR">Ошибка</option>
              </select>

              <select
                className="materials-filter"
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value as SortMode)}
                aria-label="Сортировка материалов"
              >
                <option value="newest">Сначала новые</option>
                <option value="oldest">Сначала старые</option>
                <option value="title">По названию</option>
                <option value="size">По размеру</option>
              </select>

              <button
                type="button"
                className={`materials-filter materials-filter--reset${filtersActive ? ' is-active' : ''}`}
                onClick={resetFilters}
                disabled={!filtersActive}
              >
                Сбросить фильтры
              </button>
            </div>

            <div className="materials-toolbar materials-toolbar--actions">
              <span className="materials-toolbar__selected-count">Выбрано: {selected.size}</span>

              {isCourseMode ? (
                /*
                  Область ответственности другого участника (переход/контекст курса из карточки курса).
                  Текущее видение: здесь можно показывать фиксированное поле текущего курса
                  (read-only), например название курса из URL-контекста, без возможности смены.
                  Пример:
                  <div className="materials-course-field is-readonly" title={courseTitle}>
                    <span className="materials-course-field__label">{courseTitle || 'Текущий курс'}</span>
                  </div>
                */
                <div className="materials-course-field materials-course-field--empty" aria-hidden="true" />
              ) : (
                <div className="materials-course-picker" ref={coursePickerRef}>
                  <button
                    type="button"
                    className={`materials-course-field${coursePickerOpen ? ' is-open' : ''}`}
                    onClick={() => setCoursePickerOpen((prev) => !prev)}
                    aria-haspopup="listbox"
                    aria-expanded={coursePickerOpen}
                  >
                    <span className="materials-course-field__label">
                      {selectedCourse?.title ?? 'Выберите курс'}
                    </span>
                    <span className="materials-course-field__chevron" aria-hidden="true">▾</span>
                  </button>

                  {coursePickerOpen && (
                    <div className="materials-course-picker__menu" role="listbox" aria-label="Выбор курса">
                      {coursesLoading ? (
                        <div className="materials-course-picker__empty">Загрузка курсов…</div>
                      ) : courseOptions.length === 0 ? (
                        <div className="materials-course-picker__empty">Курсы не найдены</div>
                      ) : (
                        courseOptions.map((course) => (
                          <button
                            key={course.courseId}
                            type="button"
                            role="option"
                            aria-selected={selectedCourseId === course.courseId}
                            className={`materials-course-picker__option${selectedCourseId === course.courseId ? ' is-selected' : ''}`}
                            onClick={() => {
                              setSelectedCourseId(course.courseId);
                              setCoursePickerOpen(false);
                            }}
                          >
                            {course.title}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="materials-toolbar__actions">
                <button
                  type="button"
                  className="materials-toolbar__action"
                  disabled={selected.size === 0}
                  title="Перенести выбранные материалы (заглушка)"
                  onClick={() => {
                    // Заглушка: реальный перенос материалов — ответственность другого участника/задачи.
                  }}
                >
                  Перенести
                </button>
                <button
                  type="button"
                  className="materials-toolbar__action materials-toolbar__action--danger"
                  disabled={selected.size === 0 || deleting}
                  onClick={() => void handleDeleteSelected()}
                >
                  {deleting ? 'Удаление…' : 'Удалить'}
                </button>
              </div>
            </div>

            <div className="materials-table-wrap">
              {loading ? (
                <div className="materials-state">
                  <span className="materials-state__spinner" aria-hidden="true" />
                  <p>Загружаем материалы…</p>
                </div>
              ) : listError ? (
                <div className="materials-state is-error">
                  <p>Не удалось загрузить материалы</p>
                  <span>{listError}</span>
                  <button
                    type="button"
                    className="materials-state__retry"
                    onClick={() => reload()}
                  >
                    Повторить
                  </button>
                </div>
              ) : !hasCourse ? (
                <div className="materials-state">
                  <span className="materials-state__icon">
                    <EmptyIcon />
                  </span>
                  <p>Выберите курс</p>
                  <span>Выберите курс в области выше, чтобы просмотреть его материалы.</span>
                </div>
              ) : visibleMaterials.length === 0 ? (
                <div className="materials-state">
                  <span className="materials-state__icon">
                    <EmptyIcon />
                  </span>
                  <p>{materials.length === 0 ? 'Материалов пока нет' : 'Ничего не найдено'}</p>
                  <span>
                    {materials.length === 0
                      ? 'Загрузите первый PDF или DOCX — он появится в этом списке.'
                      : 'Попробуйте изменить поисковый запрос или сбросить фильтры.'}
                  </span>
                </div>
              ) : (
                <table className="materials-table">
                  <thead>
                    <tr>
                      <th className="col-check">
                        <input
                          type="checkbox"
                          checked={allVisibleSelected}
                          onChange={toggleSelectAll}
                          aria-label="Выбрать все материалы"
                        />
                      </th>
                      <th>Название</th>
                      <th className="col-type">Тип</th>
                      <th className="col-size">Размер</th>
                      <th className="col-date">Дата загрузки</th>
                      <th className="col-status">Статус</th>
                      <th className="col-actions">Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleMaterials.map((material) => {
                      const status = normalizeStatus(material.statusMaterial);
                      const meta = STATUS_META[status];
                      const isBusy = busyId === material.materialId;

                      return (
                        <tr
                          key={material.materialId}
                          className={selected.has(material.materialId) ? 'is-selected' : undefined}
                        >
                          <td className="col-check">
                            <input
                              type="checkbox"
                              checked={selected.has(material.materialId)}
                              onChange={() => toggleSelect(material.materialId)}
                              aria-label={`Выбрать ${material.title}`}
                            />
                          </td>

                          <td>
                            <div className="material-name">
                              <span className="material-file-icon">
                                <DocIcon />
                              </span>
                              <button
                                type="button"
                                className="material-name__title"
                                onClick={() => void handleOpen(material)}
                                title={material.title}
                              >
                                {material.title}
                              </button>
                            </div>
                          </td>

                          <td className="col-type">
                            <span className="material-type-pill">{material.typeMaterial}</span>
                          </td>

                          <td className="col-size">{formatSize(material.materialSize)}</td>

                          <td className="col-date">
                            <span title={new Date(material.createdAt).toLocaleString('ru-RU')}>
                              {formatDate(material.createdAt)}
                            </span>
                          </td>

                          <td className="col-status">
                            <span className={`material-status ${meta.className}`}>
                              {status === 'PROCESSING' && (
                                <span className="material-status__spinner" aria-hidden="true" />
                              )}
                              {meta.label}
                            </span>
                          </td>

                          <td className="col-actions">
                            <div className="material-actions">
                              <button
                                type="button"
                                className="material-open"
                                onClick={() => void handleOpen(material)}
                                disabled={isBusy}
                              >
                                {isBusy ? 'Открытие…' : 'Открыть'}
                              </button>
                              <button
                                type="button"
                                className="material-icon-btn"
                                onClick={() => void handleRename(material)}
                                title="Переименовать"
                                aria-label={`Переименовать ${material.title}`}
                                disabled={isBusy}
                              >
                                <PencilIcon />
                              </button>
                              <button
                                type="button"
                                className="material-icon-btn is-danger"
                                onClick={() => void handleDelete(material)}
                                title="Удалить"
                                aria-label={`Удалить ${material.title}`}
                                disabled={isBusy}
                              >
                                <TrashIcon />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>

            <div className="materials-panel__footer">
              <span>
                Показано {visibleMaterials.length} из {totalElements}
              </span>

              {totalPages > 1 && (
                <div className="materials-pager">
                  <button
                    type="button"
                    onClick={() => {
                      setLoading(true);
                      setPage((prev) => Math.max(0, prev - 1));
                    }}
                    disabled={page === 0}
                  >
                    ← Назад
                  </button>
                  <span>
                    {page + 1} / {totalPages}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setLoading(true);
                      setPage((prev) => Math.min(totalPages - 1, prev + 1));
                    }}
                    disabled={page >= totalPages - 1}
                  >
                    Вперёд →
                  </button>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MaterialsPage;
