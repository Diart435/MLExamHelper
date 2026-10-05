CREATE TABLE event_publications (
    id UUID NOT NULL,
    completion_date TIMESTAMP WITH TIME ZONE,
    event_type VARCHAR(512) NOT NULL,
    listener_id VARCHAR(512) NOT NULL,
    publication_date TIMESTAMP WITH TIME ZONE NOT NULL,
    serialized_event TEXT NOT NULL,
    status VARCHAR(20),
    last_resubmission_date TIMESTAMP WITH TIME ZONE,
    completion_attempts INTEGER,
    PRIMARY KEY (id)
);