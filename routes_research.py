"""Coach-facing swimming research briefs.

Read-only views over what the weekly research agent produced (see
scripts/run_research.py, synthesize.py). Gated behind the Coach tier with the
app's existing coach_required check -- same gate as every other /coach page,
just without the /coach url prefix so the URLs read /research and /research/<id>.
"""
from flask import Blueprint, render_template, abort
from flask_login import login_required

from auth_utils import coach_required

research_bp = Blueprint('research', __name__)


@research_bp.route('/research')
@login_required
@coach_required
def research_list():
    from app import db
    from models import ResearchBrief

    briefs = (
        db.session.query(ResearchBrief)
        .order_by(ResearchBrief.week_of.desc(), ResearchBrief.id.desc())
        .all()
    )
    return render_template('research_list.html', briefs=briefs)


@research_bp.route('/research/<int:brief_id>')
@login_required
@coach_required
def research_brief(brief_id):
    from app import db
    from models import ResearchBrief, ResearchItem

    brief = db.session.get(ResearchBrief, brief_id)
    if not brief:
        abort(404)

    items = (
        db.session.query(ResearchItem)
        .filter_by(brief_id=brief.id)
        .order_by(ResearchItem.relevance_score.desc().nullslast(), ResearchItem.id.asc())
        .all()
    )
    return render_template('research_brief.html', brief=brief, items=items)
