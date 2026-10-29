import { useState, useMemo, type FormEvent } from 'react';
import './TestsPage.css';

/* ===================== ТИПЫ ===================== */

type TestStatus = 'done' | 'progress';

interface TestRow {
  id: number;
  name: string;
  course: string;
  date: string;
  questions: number;
  grade: number | string;
  status: TestStatus;
}

const MOCK_TESTS: TestRow[] = [
  { id: 1, name: 'Тест по всему курсу', course: 'Базы данных', date: '28.09', questions: 20, grade: 4, status: 'done' },
  { id: 2, name: 'Основы процессов', course: 'Операционные системы', date: '21.09', questions: 25, grade: '-', status: 'progress' },
  { id: 3, name: 'Процессы', course: 'Базы данных', date: '14.09', questions: 30, grade: 5, status: 'done' },
];

/* ===================== МОДАЛКА «НОВЫЙ ТЕСТ» ===================== */

interface CreateTestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: { name: string }) => void;
}

const CreateTestModal = ({ isOpen, onClose, onCreate }: CreateTestModalProps) => {
  const [name, setName] = useState('');
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Введите название теста');
      return;
    }
    onCreate({ name: name.trim() });
    onClose();
  };

  return (
    <div className="modal-overlay is-open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" onMouseDown={(e) => e.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose}>×</button>
        <h2 className="modal-title">Новый тест</h2>

        <form onSubmit={handleSubmit} noValidate>
          <div className="modal-field">
            <label className="modal-label">Название теста</label>
            <input
              className="modal-input"
              type="text"
              placeholder="Например: Тест по транзакциям"
              value={name}
              onChange={(e) => { setName(e.target.value); if (error) setError(''); }}
              autoFocus
            />
            {error && <span className="modal-error">{error}</span>}
          </div>

          <div className="modal-actions">
            <button className="modal-btn modal-btn-cancel" type="button" onClick={onClose}>
              Отмена
            </button>
            <button className="modal-btn modal-btn-create" type="submit">
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
  const [tests, setTests] = useState<TestRow[]>(MOCK_TESTS);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const filteredTests = useMemo(() => {
    return tests.filter((test) => {
      const matchSearch = test.name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchCourse = selectedCourse === 'all' || test.course === selectedCourse;
      const matchGrade = selectedGrade === 'all' || String(test.grade) === selectedGrade;
      return matchSearch && matchCourse && matchGrade;
    });
  }, [tests, searchQuery, selectedCourse, selectedGrade]);

  const handleCreateTest = (data: { name: string }) => {
    console.log('CREATE TEST:', data);
    setTests((prev) => [
      {
        id: Date.now(),
        name: data.name,
        course: '—',
        date: new Date().toLocaleDateString('ru-RU').slice(0, 5),
        questions: 0,
        grade: '-',
        status: 'progress',
      },
      ...prev,
    ]);
  };

  return (
    <div className="tests-page">
      {/* Панель фильтров */}
      <div className="filters-bar">
        <select className="filter-select" value={selectedCourse} onChange={(e) => setSelectedCourse(e.target.value)}>
          <option value="all">Все курсы</option>
          <option value="Базы данных">Базы данных</option>
          <option value="Операционные системы">Операционные системы</option>
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
                  <div className="col-course">{test.course}</div>
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
      />
    </div>
  );
};

export default TestsPage;