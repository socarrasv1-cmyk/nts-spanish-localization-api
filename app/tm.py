from typing import Dict, List, Any, Optional
from app.store import store
import uuid
from datetime import datetime


class TranslationMemory:
    """
    Translation Memory service.
    Approved TM is read-authoritative.
    New translations enter as proposals requiring explicit reviewer approval.
    """
    
    def __init__(self):
        self.store_key = "translation_memory"
    
    def search(self, source: str, locale: str = "es-US", site_id: Optional[str] = None, component: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search approved Translation Memory.
        Site-specific matches win over global matches.
        """
        tm_data = store.load(self.store_key)
        results = []
        
        for entry in tm_data.get("entries", []):
            if entry.get("source") == source and entry.get("locale") == locale and entry.get("approved"):
                # Site-specific match preferred
                if site_id and entry.get("site_id") == site_id:
                    results.insert(0, entry)
                elif not site_id or entry.get("site_id") is None:
                    results.append(entry)
        
        return results[:5]  # Return top 5 matches
    
    def propose(self, source: str, translation: str, site_id: Optional[str] = None, 
                component: Optional[str] = None, context: Optional[str] = None,
                locale: str = "es-US", notes: Optional[str] = None) -> Dict[str, Any]:
        """
        Submit a translation proposal for human review.
        """
        proposal_id = str(uuid.uuid4())
        proposal = {
            "proposal_id": proposal_id,
            "source": source,
            "translation": translation,
            "site_id": site_id,
            "component": component,
            "context": context,
            "locale": locale,
            "notes": notes,
            "status": "proposed",
            "created_at": datetime.utcnow().isoformat(),
            "reviewed_at": None,
            "reviewer": None
        }
        
        tm_data = store.load(self.store_key)
        if "proposals" not in tm_data:
            tm_data["proposals"] = []
        tm_data["proposals"].append(proposal)
        store.save(self.store_key, tm_data)
        
        return proposal
    
    def list_proposals(self, status: str = "proposed") -> List[Dict[str, Any]]:
        """
        List Translation Memory proposals by status.
        """
        tm_data = store.load(self.store_key)
        return [p for p in tm_data.get("proposals", []) if p.get("status") == status]
    
    def approve_proposal(self, proposal_id: str, reviewer: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Approve a proposal and add to approved TM.
        """
        tm_data = store.load(self.store_key)
        
        # Find proposal
        proposal = None
        for p in tm_data.get("proposals", []):
            if p.get("proposal_id") == proposal_id:
                proposal = p
                break
        
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Mark as approved
        proposal["status"] = "approved"
        proposal["reviewed_at"] = datetime.utcnow().isoformat()
        proposal["reviewer"] = reviewer
        proposal["reason"] = reason
        
        # Add to approved entries
        if "entries" not in tm_data:
            tm_data["entries"] = []
        
        approved_entry = {
            "source": proposal["source"],
            "translation": proposal["translation"],
            "site_id": proposal["site_id"],
            "component": proposal["component"],
            "context": proposal["context"],
            "locale": proposal["locale"],
            "approved": True,
            "approved_by": reviewer,
            "approved_at": datetime.utcnow().isoformat()
        }
        tm_data["entries"].append(approved_entry)
        store.save(self.store_key, tm_data)
        
        return proposal
    
    def reject_proposal(self, proposal_id: str, reviewer: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Reject a proposal.
        """
        tm_data = store.load(self.store_key)
        
        # Find proposal
        proposal = None
        for p in tm_data.get("proposals", []):
            if p.get("proposal_id") == proposal_id:
                proposal = p
                break
        
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Mark as rejected
        proposal["status"] = "rejected"
        proposal["reviewed_at"] = datetime.utcnow().isoformat()
        proposal["reviewer"] = reviewer
        proposal["reason"] = reason
        store.save(self.store_key, tm_data)
        
        return proposal
