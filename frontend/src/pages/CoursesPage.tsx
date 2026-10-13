import { useState, useMemo } from 'react';
import './CoursesPage.css';


interface Course {
  id: number;
  title: string;
  materialsCount: number;
  testsCount: number;
  progress: number;
}
// тут как-то запрос к апишке
const MOCK_COURSES: Course[] = [
  { id: 1, title: 'Базы данных', materialsCount: 12, testsCount: 3, progress: 72 },
  { id: 2, title: 'Операционные системы', materialsCount: 8, testsCount: 2, progress: 45 },
  { id: 3, title: 'Английский язык', materialsCount: 15, testsCount: 5, progress: 88 },
];

type SortOption = 'newest' | 'progress';

const CoursesPage = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortOption>('newest');
  const [isLoading] = useState(false);

  const filteredCourses = useMemo(() => {
    let result = [...MOCK_COURSES];
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter((c) => c.title.toLowerCase().includes(q));
    }
    if (sortBy === 'progress') {
      result.sort((a, b) => b.progress - a.progress);
    }
    return result;
  }, [searchQuery, sortBy]);

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

          <button className="btn-create-course">+ Создать курс</button>
        </div>
      </header>

      {/* Сетка карточек */}
      <main className="courses-grid">
        {isLoading ? (
          // Скелетоны (можно добавить позже)
          <div className="skeleton-loader">Загрузка...</div>
        ) : filteredCourses.length === 0 ? (
          <div className="empty-state">Курсы не найдены</div>
        ) : (
          filteredCourses.map((course) => (
            <article key={course.id} className="course-card">
              <div className="card-header">
                <h3 className="card-title">{course.title}</h3>
                {/* Черный квадратик с цифрой (как на дизайне) */}
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
    </div>
  );
};

export default CoursesPage;