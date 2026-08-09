package com.hhkim88.typofix.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.hhkim88.typofix.R
import com.hhkim88.typofix.data.TypoCorrectionEntity
import com.hhkim88.typofix.databinding.ItemCorrectionBinding

class CorrectionsAdapter(
    private val onToggle: (TypoCorrectionEntity, Boolean) -> Unit,
    private val onDelete: (TypoCorrectionEntity) -> Unit
) : ListAdapter<TypoCorrectionEntity, CorrectionsAdapter.ViewHolder>(DIFF) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemCorrectionBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(private val binding: ItemCorrectionBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(item: TypoCorrectionEntity) {
            binding.pairText.text = "${item.typo} → ${item.correction}"
            binding.countText.text = binding.root.context.getString(R.string.corrections_count_format, item.count)

            binding.enabledSwitch.setOnCheckedChangeListener(null)
            binding.enabledSwitch.isChecked = item.enabled
            binding.enabledSwitch.setOnCheckedChangeListener { _, isChecked ->
                onToggle(item, isChecked)
            }

            binding.deleteButton.setOnClickListener { onDelete(item) }
        }
    }

    companion object {
        private val DIFF = object : DiffUtil.ItemCallback<TypoCorrectionEntity>() {
            override fun areItemsTheSame(oldItem: TypoCorrectionEntity, newItem: TypoCorrectionEntity) =
                oldItem.typo == newItem.typo

            override fun areContentsTheSame(oldItem: TypoCorrectionEntity, newItem: TypoCorrectionEntity) =
                oldItem == newItem
        }
    }
}
