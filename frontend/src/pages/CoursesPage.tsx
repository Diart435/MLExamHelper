import { useState, useMemo, useEffect, type FormEvent } from 'react';
import './CoursesPage.css';

interface Course {
  id: number;
  title: string;
  description?: string;
  materialsCount: number;
  testsCount: number;
  progress: number;
}

const MOCK_COURSES: Course[] = [
  { id: 1, title: 'Базы данных', materialsCount: 12, testsCount: 3, progress: 72 },
  { id: 2, title: 'Операционные системы', materialsCount: 8, testsCount: 2, progress: 45 },
  { id: 3, title: 'Английский язык', materialsCount: 15, testsCount: 5, progress: 88 },
];

type SortOption = 'newest' | 'progress';

/* ===================== МОДАЛКА ===================== */

interface CreateCourseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: { name: string; description: string; files: File[] }) => void;
}

const CreateCourseModal = ({ isOpen, onClose, onCreate }: CreateCourseModalProps) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState('');

  // Блокируем прокрутку фона + Esc закрывает
  useEffect(() => {
    if (!isOpen) return;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);

    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener('keydown', onKey);
    };
  }, [isOpen, onClose]);

  // Сбрасываем форму при открытии
  useEffect(() => {
    if (isOpen) {
      setName('');
      setDescription('');
      setFiles([]);
      setError('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles(Array.from(list));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Введите название курса');
      return;
    }
    onCreate({ name: trimmed, description: description.trim(), files });
    onClose();
  };

  return (
    <div
      className="modal-overlay is-open"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      onMouseDown={(e) => {
        // закрываем только если кликнули именно по фону, а не по карточке
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть">
          ×
        </button>

        <h2 className="modal-title" id="modal-title">Название курса</h2>

        <form onSubmit={handleSubmit} noValidate>
          <div className="modal-field">
            <label className="modal-label" htmlFor="cc-name">Название</label>
            <input
              id="cc-name"
              className="modal-input"
              type="text"
              placeholder="Например: Базы данных"
              value={name}
              onChange={(e) => { setName(e.target.value); if (error) setError(''); }}
              autoFocus
            />
            {error && <span className="modal-error">{error}</span>}
          </div>

          <div className="modal-field">
            <label className="modal-label" htmlFor="cc-desc">Описание</label>
            <textarea
              id="cc-desc"
              className="modal-textarea"
              placeholder="Кратко опишите, чему посвящён курс"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="modal-upload">
            <span className="modal-upload-icon">📎</span>
            <div className="modal-upload-title">Загрузите материалы</div>
            <div>Перетащите файлы сюда или нажмите, чтобы выбрать</div>
            <input
              type="file"
              multiple
              hidden
              id="cc-files"
              onChange={(e) => handleFiles(e.target.files)}
            />
            <label htmlFor="cc-files" className="modal-upload-link">Выбрать файлы</label>
            {files.length > 0 && (
              <div className="modal-files-list">
                {files.map((f) => (
                  <div key={f.name + f.size} className="modal-file-item">
                    📄 {f.name}
                  </div>
                ))}
              </div>
            )}
          </div>

          <p className="modal-upload-note">Материалы можно будет загрузить позже</p>

          <div className="modal-actions">
            <button className="modal-btn modal-btn-cancel" type="button" onClick={onClose}>
              Отмена
            </button>
            <button className="modal-btn modal-btn-create" type="submit">
              Создать курс
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

/* ===================== СТРАНИЦА ===================== */

const CoursesPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('newest');
  const [isLoading] = useState(false);
  const [courses, setCourses] = useState<Course[]>(MOCK_COURSES);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const filteredCourses = useMemo(() => {
    let result = [...courses];
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter((c) => c.title.toLowerCase().includes(q));
    }
    if (sortBy === 'progress') {
      result.sort((a, b) => b.progress - a.progress);
    }
    return result;
  }, [courses, searchQuery, sortBy]);

  const handleCreateCourse = (data: { name: string; description: string; files: File[] }) => {
    // TODO: заменить на реальный POST /api/courses (FormData с files)
    console.log('CREATE COURSE:', {
      name: data.name,
      description: data.description,
      files: data.files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
    });

    setCourses((prev) => [
      {
        id: Date.now(),
        title: data.name,
        description: data.description,
        materialsCount: data.files.length,
        testsCount: 0,
        progress: 0,
      },
      ...prev,
    ]);
  };

  return (
    <div className="courses-page">
      <header className="courses-header">
        <h1 className="page-title"></h1>

        <div className="controls-bar">
          <input
            type="text"
            placeholder="Поиск по курсам..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="sort-select"
          >
            <option value="newest">Сначала новые</option>
            <option value="progress">По прогрессу</option>
          </select>

          <button className="btn-create-course" onClick={() => setIsModalOpen(true)}>
            + Создать курс
          </button>
        </div>
      </header>

      <main className="courses-grid">
        {isLoading ? (
          <div className="skeleton-loader">Загрузка...</div>
        ) : filteredCourses.length === 0 ? (
          <div className="empty-state">Курсы не найдены</div>
        ) : (
          filteredCourses.map((course) => (
            <article key={course.id} className="course-card">
              <div className="card-header">
                <h3 className="card-title">{course.title}</h3>
                <span className="card-badge">{course.testsCount}</span>
              </div>

              <ul className="card-stats-list">
                <li>• {course.materialsCount} материалов</li>
                <li>• {course.testsCount} теста</li>
              </ul>

              <div className="progress-section">
                <div className="progress-label">
                  <span>Готовность к сессии - {course.progress}%</span>
                </div>
                <div className="progress-bar-bg">
                  <div
                    className="progress-bar-fill"
                    style={{ width: `${course.progress}%` }}
                  />
                </div>
              </div>

              <div className="card-actions">
                <button className="btn-open">Открыть</button>
                <button className="btn-create-test">Создать тест</button>
              </div>
            </article>
          ))
        )}
      </main>

      <CreateCourseModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateCourse}
      />
    </div>
  );
};

export default CoursesPage;