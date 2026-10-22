import { useState, useMemo, useEffect, type FormEvent } from 'react';
// 1. ДОБАВЬТЕ ИМПОРТ ФУНКЦИИ УДАЛЕНИЯ ИЗ ВАШЕГО API ФАЙЛА
import { deleteCourse } from '../api/courses'; 
import './CoursesPage.css';

/* ===================== ТИПЫ ===================== */

interface Course {
  // 2. ИСПРАВИЛИ ТИП ID НА STRING (UUID) ДЛЯ СОВМЕСТИМОСТИ С БЭКЕНДОМ
  id: string; 
  title: string;
  description?: string;
  materialsCount: number;
  testsCount: number;
  progress: number;
}

type MaterialStatus = 'done' | 'progress' | 'error';
type MaterialKind = 'PDF' | 'Текст' | 'Ссылка' | 'Документ';

interface MaterialItem {
  id: string;
  name: string;
  kind: MaterialKind;
  status: MaterialStatus;
}

interface TestItem {
  id: string;
  name: string;
  date: string;
  questions: number;
  grade: number;
}

const MOCK_COURSES: Course[] = [
  // 3. ОБНОВИЛИ МОКОВЫЕ ДАННЫЕ ПОД НОВЫЙ ТИП ID
  { 
    id: '550e8400-e29b-41d4-a716-446655440000', 
    title: 'Базы данных', 
    materialsCount: 12, 
    testsCount: 3, 
    progress: 72 
  },
];

type SortOption = 'newest' | 'progress';

/* ===================== МОДАЛКА «СОЗДАНИЕ КУРСА» ===================== */

interface CreateCourseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: { name: string; description: string }) => void;
}

const CreateCourseModal = ({ isOpen, onClose, onCreate }: CreateCourseModalProps) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener('keydown', onKey);
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      setName('');
      setDescription('');
      setError('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Введите название курса');
      return;
    }
    onCreate({ name: trimmed, description: description.trim() });
    onClose();
  };

  // handleDeleteCourse УДАЛЕН ОТСЮДА, так как это не место для него

  return (
    <div
      className="modal-overlay is-open"
      role="dialog"
      aria-modal="true"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть">
          ×
        </button>

        <h2 className="modal-title">Название курса</h2>

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

          <div className="modal-actions" style={{ marginTop: '32px' }}>
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

/* ===================== СТРАНИЦА КУРСА ===================== */

interface CourseViewProps {
  onBack: () => void;
}

const CourseView = ({ onBack }: CourseViewProps) => {
  const materials: MaterialItem[] = [
    { id: 'm1', name: 'Конспект_Лекция_1.pdf', kind: 'PDF', status: 'done' },
    { id: 'm2', name: 'Транзакция_и_индексы.pdf', kind: 'PDF', status: 'done' },
    { id: 'm3', name: 'Лекция_sql_.txt', kind: 'Текст', status: 'progress' },
    { id: 'm4', name: 'Статья про нормализацию', kind: 'Ссылка', status: 'done' },
    { id: 'm5', name: 'Схема_БД.docx', kind: 'Документ', status: 'error' },
  ];

  const tests: TestItem[] = [
    { id: 't1', name: 'Тест по всему курсу', date: '10.09', questions: 10, grade: 4 },
    { id: 't2', name: 'Транзакции', date: '20.09', questions: 20, grade: 4 },
  ];

  return (
    <div className="course-page">
      <div className="course-columns">
        {/* ЛЕВАЯ КОЛОНКА: МАТЕРИАЛЫ */}
        <section className="course-panel">
          <h2 className="panel-title">Материалы</h2>
          
          {/* Чёрная кнопка из макета */}
          <button className="btn-open-black" type="button">
            Открыть материалы
          </button>

          <div className="materials-list" style={{ marginTop: '20px' }}>
            {materials.length === 0 && (
              <div className="empty-state">Пока нет материалов</div>
            )}
            {materials.map((m) => (
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
            ))}
          </div>
        </section>

        {/* ПРАВАЯ КОЛОНКА: ТЕСТЫ */}
        <section className="course-panel">
          <h2 className="panel-title">Тесты курса</h2>

          {/* Чёрная кнопка из макета */}
          <button className="btn-open-black" type="button">
            Открыть тесты
          </button>

          <div className="tests-list" style={{ marginTop: '20px' }}>
            {tests.length === 0 && (
              <div className="empty-state">Пока нет тестов</div>
            )}
            {tests.map((t) => (
              <div key={t.id} className="test-row">
                <div className="test-body">
                  <p className="test-name">{t.name}</p>
                  <span className="test-meta">{t.date} · {t.questions} вопросов</span>
                </div>
                <div className="test-grade" title="Оценка">{t.grade}</div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <button className="btn-back" type="button" onClick={onBack}>
        ← Ко всем курсам
      </button>
    </div>
  );
};

/* ===================== ГЛАВНЫЙ КОМПОНЕНТ ===================== */

const CoursesPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('newest');
  const [isLoading] = useState(false);
  const [courses, setCourses] = useState<Course[]>(MOCK_COURSES);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [openedCourse, setOpenedCourse] = useState<Course | null>(null);


  // 5. ПЕРЕНОСИМ ЛОГИКУ УДАЛЕНИЯ СЮДА
  const handleDeleteCourse = async (courseId: string) => {
    if (!window.confirm('Вы уверены, что хотите удалить этот курс?')) {
      return;
    }

    try {
      await deleteCourse(courseId);
      // Обновляем локальный стейт, удалив курс из массива
      setCourses((prev) => prev.filter((c) => c.id !== courseId));
    } catch (err: any) {
      console.error('Ошибка удаления курса:', err);
      const errorMsg = err.response?.data?.message || 'Не удалось удалить курс';
      alert(errorMsg);
    }
  };

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

  const handleCreateCourse = (data: { name: string; description: string }) => {
    console.log('CREATE COURSE:', data);
    setCourses((prev) => [
      {
        // 6. ИСПОЛЬЗУЕМ STRING ID ДЛЯ ЕДИНООБРАЗИЯ
        id: Date.now().toString(), 
        title: data.name,
        description: data.description,
        materialsCount: 0,
        testsCount: 0,
        progress: 0,
      },
      ...prev,
    ]);
  };

  if (openedCourse) {
    return <CourseView onBack={() => setOpenedCourse(null)} />;
  }

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
                <button
                  className="btn-open"
                  type="button"
                  onClick={() => setOpenedCourse(course)}
                >
                  Открыть
                </button>
                <button 
                  className="btn-delete" 
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    // 7. ТЕПЕРЬ ЭТА ФУНКЦИЯ ВИДИТ handleDeleteCourse
                    handleDeleteCourse(course.id);
                  }}
                >
                  Удалить
                </button>
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