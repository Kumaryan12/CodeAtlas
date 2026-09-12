from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from codeatlas.dependencies.graph import build_graph
from codeatlas.models.repository import Repository, RepositoryFile
from codeatlas.parsers.types import ResolutionConfig
from codeatlas.schemas.graph import DependencyGraph, GraphFile


def snapshot_graph(session: Session, repository: Repository) -> DependencyGraph:
    files = session.scalars(
        select(RepositoryFile)
        .options(defer(RepositoryFile.source, raiseload=True))
        .where(RepositoryFile.repository_id == repository.id)
    )
    return build_graph(
        repository.id,
        [GraphFile.model_validate(file, from_attributes=True) for file in files],
        [ResolutionConfig.model_validate(config) for config in repository.resolution_configs]
        if repository.resolution_configs is not None
        else None,
    )


def snapshot_data_flow(session: Session, repository: Repository) -> DependencyGraph:
    from codeatlas.dependencies.data_flow import build_data_flow

    graph = snapshot_graph(session, repository)
    files = session.scalars(
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repository.id)
        .order_by(RepositoryFile.path)
    ).all()
    return build_data_flow(files, graph)
