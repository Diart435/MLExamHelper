import { useState, useMemo, useEffect, type FormEvent } from 'react';
import './TestsPage.css';
import { useNavigate } from 'react-router-dom';

// Импортируем API курсов, чтобы получить реальный список
import { coursesApi } from '../api/courses'; 

/* ===================== ТИПЫ ===================== */

type TestStatus = 'done' | 'progress';

interface TestRow {
  id: string; // Лучше использовать string для UUID
  name: string;
  courseId: string;
  courseName: string;
  date: string;
  questions: number;
  grade: number | string;
  status: TestStatus;
}

const MOCK_TESTS: TestRow[] = [
  { id: 't1', name: 'Тест по всему курсу', courseId: 'c1', courseName: 'Базы данных', date: '28.09', questions: 20, grade: 4, status: 'done' },
  { id: 't2', name: 'Основы процессов', courseId: 'c2', courseName: 'Операционные системы', date: '21.09', questions: 25, grade: '-', status: 'progress' },
];

/* ===================== МОДАЛКА «НОВЫЙ ТЕСТ» ===================== */

interface CreateTestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: { courseId: string; courseName: string }) => void;
  courses: { id: string; title: string }[]; // Список курсов из БД
}

const CreateTestModal = ({ isOpen, onClose, onCreate, courses }: CreateTestModalProps) => {
  const [selectedCourseId, setSelectedCourseId] = useState('');
  const [error, setError] = useState('');

  // Сбрасываем состояние при открытии/закрытии
  useEffect(() => {
    if (isOpen) {
      setSelectedCourseId('');
      setError('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selectedCourseId) {
      setError('Пожалуйста, выберите курс из списка');
      return;
    }
    
    const course = courses.find(c => c.id === selectedCourseId);
    if (course) {
      onCreate({ courseId: course.id, courseName: course.title });
    }
  };

  return (
    <div className="modal-overlay is-open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose}>×</button>
        <h2 className="modal-title">Новый тест</h2>

        <form onSubmit={handleSubmit} noValidate>
          <div className="modal-field">
            <label className="modal-label">Выберите курс</label>
            
            {courses.length === 0 ? (
              <div className="modal-error" style={{ marginBottom: '10px' }}>
                У вас пока нет созданных курсов. Сначала создайте курс.
              </div>
            ) : (
              <select
                className="modal-input"
                value={selectedCourseId}
                onChange={(e) => { setSelectedCourseId(e.target.value); if (error) setError(''); }}
                autoFocus
                style={{ cursor: 'pointer' }}
              >
                <option value="" disabled>— Выберите курс из списка —</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.title}
                  </option>
                ))}
              </select>
            )}
            
            {error && <span className="modal-error">{error}</span>}
          </div>

          <div className="modal-actions">
            <button className="modal-btn modal-btn-cancel" type="button" onClick={onClose}>
              Отмена
            </button>
            <button 
              className="modal-btn modal-btn-create" 
              type="submit"
              disabled={courses.length === 0}
            >
              Перейти к созданию
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

/* ===================== ГЛАВНЫЙ КОМПОНЕНТ ===================== */

const TestsPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCourse, setSelectedCourse] = useState('all');
  const [selectedGrade, setSelectedGrade] = useState('all');
  const [tests] = useState<TestRow[]>(MOCK_TESTS);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const navigate = useNavigate();
  // Состояние для хранения реальных курсов из БД
  const [availableCourses, setAvailableCourses] = useState<{ id: string; title: string }[]>([]);

  // Загружаем список курсов при монтировании компонента
  useEffect(() => {
    const fetchCoursesForSelect = async () => {
      try {
        // Запрашиваем большой размер страницы, чтобы получить все курсы для выпадающего списка
        const response = await coursesApi.getAll({ page: 0, size: 100 });
        const coursesList = response.content.map(c => ({ 
          id: c.courseId, 
          title: c.title 
        }));
        setAvailableCourses(coursesList);
      } catch (err) {
        console.error('Не удалось загрузить список курсов:', err);
      }
    };
    
    fetchCoursesForSelect();
  }, []);

  const filteredTests = useMemo(() => {
    return tests.filter((test) => {
      const matchSearch = test.name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchCourse = selectedCourse === 'all' || test.courseName === selectedCourse;
      const matchGrade = selectedGrade === 'all' || String(test.grade) === selectedGrade;
      return matchSearch && matchCourse && matchGrade;
    });
  }, [tests, searchQuery, selectedCourse, selectedGrade]);

  const handleCreateTest = (data: { courseId: string; courseName: string }) => {
  navigate(`/courses/${data.courseId}/tests/create`);
};

  // Получаем уникальные названия курсов для фильтра сверху
  const uniqueCourses = useMemo(() => {
    const courses = new Set(tests.map(t => t.courseName));
    return Array.from(courses);
  }, [tests]);

  return (
    <div className="tests-page">
      {/* Панель фильтров */}
      <div className="filters-bar">
        <select className="filter-select" value={selectedCourse} onChange={(e) => setSelectedCourse(e.target.value)}>
          <option value="all">Все курсы</option>
          {uniqueCourses.map(course => (
            <option key={course} value={course}>{course}</option>
          ))}
        </select>

        <select className="filter-select filter-select--purple" value={selectedGrade} onChange={(e) => setSelectedGrade(e.target.value)}>
          <option value="all">Все оценки</option>
          <option value="5">5</option>
          <option value="4">4</option>
          <option value="3">3</option>
          <option value="2">2</option>
        </select>

        <div className="grade-filters">
          {[5, 4, 3, 2].map((g) => (
            <button
              key={g}
              className={`grade-btn ${selectedGrade === String(g) ? 'active' : ''}`}
              onClick={() => setSelectedGrade(selectedGrade === String(g) ? 'all' : String(g))}
            >
              {g}
            </button>
          ))}
        </div>

        <input
          type="text"
          className="search-input"
          placeholder="Поиск по названию"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />

        <button className="btn-create-test" onClick={() => setIsModalOpen(true)}>
          + Создать тест
        </button>
      </div>

      {/* Таблица тестов с ушком */}
      <div className="tabbed-section">
        <h2 className="panel-title tab-header">Все тесты</h2>
        
        <div className="course-panel tabbed-panel">
          <div className="table-head">
            <div className="col-name">Название</div>
            <div className="col-course">Курс</div>
            <div className="col-date">Дата</div>
            <div className="col-questions">Вопросов</div>
            <div className="col-grade">Оценка</div>
            <div className="col-status">Статус</div>
            <div className="col-actions">Действия</div>
          </div>

          <div className="table-body">
            {filteredTests.length === 0 ? (
              <div className="empty-state">Тесты не найдены</div>
            ) : (
              filteredTests.map((test) => (
                <div key={test.id} className="table-row">
                  <div className="col-name font-medium">{test.name}</div>
                  <div className="col-course">{test.courseName}</div>
                  <div className="col-date">{test.date}</div>
                  <div className="col-questions">{test.questions}</div>
                  
                  <div className="col-grade">
                    {test.grade !== '-' ? (
                      <span className="grade-badge">{test.grade}</span>
                    ) : (
                      <span className="grade-badge grade-badge--empty">-</span>
                    )}
                  </div>
                  
                  <div className="col-status">
                    {test.status === 'done' ? (
                      <span className="status-badge status-badge--done">Завершён</span>
                    ) : (
                      <span className="status-badge status-badge--progress">В процессе</span>
                    )}
                  </div>

                  <div className="col-actions">
                    {test.status === 'done' ? (
                      <>
                        <button className="action-btn">Разбор</button>
                        <button className="action-btn">Удалить</button>
                      </>
                    ) : (
                      <button className="action-btn action-btn--wide">Продолжить</button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Модалка */}
      <CreateTestModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateTest}
        courses={availableCourses}
      />
    </div>
  );
};

export default TestsPage;