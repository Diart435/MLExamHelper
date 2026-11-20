import { useParams, useNavigate } from 'react-router-dom';
import './MaterialsPage.css';

const MaterialsPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();

  if (!courseId) {
    return (
      <div className="materials-page">
        <div className="materials-page__pattern" aria-hidden="true" />
        <div className="materials-page__content">
          <div className="materials-state is-error">
            <p>Курс не найден</p>
            <span>Вернитесь к списку курсов и откройте материалы нужного курса.</span>
            <button
              type="button"
              className="materials-state__retry"
              onClick={() => navigate('/courses')}
            >
              Ко всем курсам
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="materials-page">
      <div className="materials-page__pattern" aria-hidden="true" />

      <div className="materials-page__content">
        <section className="materials-block">
          <div className="materials-tab">Загрузка материала</div>
          <div className="materials-panel materials-panel--upload">
            <div className="materials-placeholder">
              Панель загрузки материалов курса будет доступна здесь.
            </div>
          </div>
        </section>

        <section className="materials-block">
          <div className="materials-tab">
            Материалы
            <span className="materials-tab__count">0</span>
          </div>
          <div className="materials-panel materials-panel--list">
            <div className="materials-placeholder">
              Список материалов курса появится здесь.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MaterialsPage;
